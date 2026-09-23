---
name: vcmi-mapgen-pipeline
description: "VCMI map-generator pipeline & step architecture — the PipelineStep contract (constructor + inject() + parameterless run()), the render-only MapState, PlacementWorkspace's separate shared-state channel, PipelineBuilder's hand-wired DI, and cli.py's fixed-preset-vs-configurable subcommand split. Load when adding/changing a step, wiring a new cli.py subcommand, or touching pipeline.py/pipeline_builder.py."
metadata:
  generated_by: farrier
  source: library/skills/projects/vcmi-mapgen/vcmi-mapgen-pipeline/SKILL.md
  resolve: "farrier source .claude/skills/vcmi-mapgen-pipeline/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
  tags: [python, backend, standards, architecture]
---

# VCMI map-generator — pipeline & step architecture

Two otherwise-unrelated pipelines — the procedural generator (`terrain_gen -> tile ->
segment -> gate? -> gameplay -> vegetation -> pickup -> repair`) and the identity-rebuild
engine (`extract_template -> rebuild_map/deform_warp -> verify? -> fm_document`) — share
one step contract and one hand-wired builder. Read `vcmi-mapgen-maps` for what each step
domain-wise implements; this skill is about how they're wired together.

## The step contract (`pipeline.PipelineStep`)

A step owns its data as **instance properties**, never a shared mutable object passed
into `run()`:

- **Constructor** — compile-time-known config only (seed, size, subterrain flag, a map
  name, `identity: bool`, ...). Whatever the CLI/builder already knows before any step runs.
- **`inject(self, **kwargs)`** — values an *earlier* step produced. The keyword parameter
  names ARE the step's declared manifest of what it needs (typed, named — not a generic
  dict). Override the base no-op with exactly the named kwargs you need; don't accept `**kwargs`
  loosely.
- **`run(self) -> None`** — takes nothing, computes the step's own output properties from
  what the constructor and `inject()` gave it.

```python
class TileStep(PipelineStep):
    def __init__(self, size: int = 72) -> None:
        self.size = size
        self.cells: dict = {}          # output property
        self._input_grids: dict = {}   # set by inject()

    def inject(self, *, grids: dict, tunnel_protect) -> None:
        self._input_grids = grids
        self._tunnel_protect = frozenset(tunnel_protect)

    def run(self) -> None:
        ...  # self.cells = ...
```

Never reintroduce `run(state, ontology)` or any shared object threaded through every
step — that was the pre-refactor `zone_engine.py`/`VcmiMapGenPipeline` shape and is
exactly what this contract replaced.

## MapState is render-only, not a working-state bag

`pipeline.MapState` holds exactly what `renderers/png.py`'s `PngRenderer`,
`renderers/overlays/*`'s `MapOverlay`, and `renderers/vmap.py`'s `VmapRenderer` read —
`size / surfs / cells / zones / gate_blk / objs / player_towns` — nothing else. No step
holds or mutates a `MapState`; `PipelineBuilder` assembles one explicitly, by name, from
specific finished steps' properties, purely for the render phase. **Adding a new step
must never require adding a field to `MapState`** — if a step's output needs to reach a
renderer, that's a sign it belongs in the existing fields (`objs`, `zones`, ...), not a
reason to widen the schema.

## `PlacementWorkspace` is a separate, deliberate exception

`GameplayStep`/`VegetationStep`/`PickupStep`/`RepairStep` share a `PlacementWorkspace`
(constructor-injected by reference, holding `LevelWorkspace`/`ZoneWorkspace` per level/zone)
that they mutate in place across the four steps — `GameplayStep` populates
`zw.occupied/gobjs/prot/...`, `VegetationStep` fills `zw.open_set/blocked/passable`,
`PickupStep` writes `zw.reach/used`. This is **not** the `inject()` channel and not
`MapState` — it's a third, narrower pattern for exactly this one tightly-coupled step
family. Don't generalize it to other steps and don't route its data through `inject()`
instead; it already IS the injected dependency (passed once, at construction).

This coupling is why `--stop-after` (below) is a prefix cut and not an arbitrary
skip-list: `PickupStep` reads `zw.open_set` assuming `VegetationStep` already populated
it. Skip `vegetation` and `PickupStep` sees the `ZoneWorkspace` dataclass defaults
(empty frozensets) instead of a real gap — a silent wrong-answer, not an error.

## `PipelineBuilder` — hand-wired DI, no framework

`pipeline_builder.PipelineBuilder` has one method per subcommand family. Each method is a
straight-line function: construct a step, `run()` it, read back whichever of its
properties a later step needs, call that step's `inject()`, `run()` it, repeat. No
registry, no reflection, no generic "shared dict" — every wire is written out by hand and
readable top to bottom.

- `run_generate(...)` — the procedural pipeline. Accepts `stop_after` (one of
  `GENERATE_STOP_POINTS`), a **prefix cut**: run steps up to and including the named one,
  return early. This is the only skip mechanism that exists, and it exists only here —
  see the `PlacementWorkspace` note above for why an interior skip-list isn't safe.
- `run_identity_rebuild(...)` / `run_deform_rebuild(...)` — the identity-rebuild pipeline.
  Fixed sequences; not CLI-configurable at all.

## `cli.py`'s fixed-preset vs. configurable split

Every subcommand except `generate` (`extract` / `inspect` / `features` / `rebuild` /
`run`) is a **fixed** `PipelineBuilder`-assembled preset — same behavior every time, no
flags select steps/overlays/renderers. Only `generate` takes `--overlays` / `--renderers`
/ `--stop-after`. Don't add step-skipping or overlay/renderer selection to any other
subcommand — that configurability was a deliberate, scoped decision for `generate` alone,
not a pattern to extend.

`VerifyStep` is never skippable once a preset includes it (`rebuild --verify`, `run`
always verifies) — there is no flag that can omit it from a preset that has it, protecting
the bit-exact identity guarantee (see `vcmi-mapgen-maps`).

`render-ontology` stays outside this entire model — it renders the object taxonomy
itself (`renderers/ontology_render.py`), never touches a generated/rebuilt map, and
`cli.py` calls it directly with no `PipelineBuilder` involvement.

## Adding a new step

1. New subpackage `steps/<name>/` — `step.py` with the class, an **empty**
   `__init__.py` (the convention here: subpackage `__init__.py`s are empty; the
   *top-level* `steps/__init__.py` does all the re-exporting).
2. Register it in `steps/__init__.py`'s explicit import + `__all__` list — steps are not
   auto-discovered.
3. Wire it into whichever `PipelineBuilder` method needs it, by hand.
4. If its output must reach a renderer, thread it through `MapState`'s *existing* fields;
   don't add a new one (see above).

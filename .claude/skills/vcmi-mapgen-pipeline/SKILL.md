---
name: vcmi-mapgen-pipeline
description: "VCMI map-generator pipeline & step architecture — the PipelineStep contract (constructor + inject() + run(ontology, map_state)), the render-only MapState, the ProviderRegistry that replaces raw ctx-dict keys, PlacementWorkspace's shared-state channel, and cli.py's fixed-preset-vs-configurable subcommand split. Load when adding/changing a step, wiring a new cli.py subcommand, or touching pipeline.py."
metadata:
  generated_by: farrier
  source: library/skills/projects/vcmi-mapgen/vcmi-mapgen-pipeline/SKILL.md
  resolve: "farrier source .claude/skills/vcmi-mapgen-pipeline/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
  tags: [python, backend, standards, architecture]
---

# VCMI map-generator — pipeline & step architecture

One pipeline — the procedural generator (`terrain_gen -> segment -> gate? -> gameplay ->
vegetation -> pickup -> repair`) — built from an ordered list of `PipelineStep`s run by
`Pipeline`. Read `vcmi-mapgen-maps` for what each step domain-wise implements; this skill
is about how they're wired together. (There used to be a second, identity-rebuild
pipeline sharing this contract — it was deleted; the generator's corpus statistics are
unaffected, since the corpus only ever fed spatial priors, never map content.)

## The step contract (`pipeline.PipelineStep`)

A step owns its data as **instance properties**, never a shared mutable object passed
into `run()`:

- **Constructor** — compile-time-known config only (seed, size, subterrain flag, ...).
  Whatever the CLI already knows before any step runs.
- **`inject(self, ctx)`** — pull exactly the values this step needs out of the shared
  `ProviderRegistry` (see below), typed by their own dataclass, and store them on self.
- **`run(self, ontology, map_state)`** — `ontology` and `map_state` are ALWAYS passed,
  whether or not this step uses them. **Every step's `run()` must write onto
  `map_state`** — see the next section; there are no ctx-only steps.

```python
@dataclass
class TerrainGrids:
    grids: dict = field(default_factory=dict)
    tunnel_protect: frozenset = frozenset()

class TerrainStep(PipelineStep):
    def __init__(self, size: int = 72) -> None:
        self.size = size
        self.cells: dict = {}          # output property
        self._ctx = None

    def inject(self, ctx) -> None:
        self._ctx = ctx                # stored for run() to `.provide()` into later

    def run(self, ontology, map_state) -> None:
        ...
        map_state.cells = self.cells                    # the step's real job
        self._ctx.provide(TerrainGrids(grids=..., tunnel_protect=...))  # for later steps
```

Never reintroduce a shared mutable object threaded through every step's `run()` in place
of `map_state`/the registry — that was the pre-refactor `zone_engine.py`/
`VcmiMapGenPipeline` shape and is exactly what this contract replaced.

## No ctx-only steps — every step must modify `MapState`

A step exists to advance the map, not to compute an intermediate value for the next step
in line. If you find a `PipelineStep` whose `run()` never touches `map_state`, one of two
things happened, and both are fixable without an exception to the rule:

1. **An artificial split** — the value has exactly one consumer, and it's the very next
   step in the list. This is what the old `TerrainGenStep`/`TileStep` split was:
   `TerrainGenStep` generated a raw macro grid into ctx; `TileStep`, run immediately next,
   was its only reader and immediately superseded the value with its own tiled version.
   They're now one step (`TerrainStep`). **Fix: merge the two steps.**
2. **A genuinely shared cross-step value with no map-level meaning of its own** (e.g.
   `TerrainGrids`, `PlacementWorkspace`) — but the step that computes it ALSO has real
   `map_state` work to do, so it publishes the value as a side effect of an
   already-legitimate step's `run()`, never as the step's only reason to exist.

See `vcmi_mapgen/steps/AGENTS.md` for the full contract and worked examples.

## `ProviderRegistry` replaces raw ctx-dict keys

`Pipeline.ctx` is a `ProviderRegistry`: type-keyed, memoized-per-run values, not a
string-keyed dict. A producing step's `run()` calls `self._ctx.provide(SomeResult(...))`
once it has computed a typed dataclass result. A later step's `inject()` reads it back:

- `ctx.require(SomeResult)` — the producing step is guaranteed to have already run;
  raises `MissingProviderError` otherwise (always a wiring bug, never worked around).
- `ctx.get(SomeResult, SomeResult())` — the producing step might not be in the pipeline
  at all (e.g. `GateStep` only runs for subterrain maps; its consumers read `GateResult`'s
  empty default instead of erroring).
- `ctx.get_or_create(SomeType, SomeType)` — the *first* demander creates the value and
  every later demander mutates that SAME instance further (`PlacementWorkspace`).

Dataclasses live next to the step that produces them (`GateResult` in
`steps/gate/step.py`, `PickupIndex` in `steps/pickup/step.py`, ...), not in a shared
`results.py` — there's no central registry of types to keep in sync, just an import.

Sequencing is untouched by any of this: `add_step()` order is still hand-written and
still matters (MapState/workspace mutation order and RNG determinism depend on it). The
registry only changes how a value crosses from one already-ordered step to a later one;
it is not a dependency graph, and it never lets a step run out of its list position.

## MapState is render-only, not a working-state bag

`pipeline.MapState` (in `vcmi_mapgen/models/map_state.py`) holds exactly what
`renderers/png.py`'s `PngRenderer`, `renderers/overlays/*`'s `MapOverlay`, and
`renderers/vmap.py`'s `VmapRenderer` read — `size / surfs / cells / zones / gate_blk /
objs / player_towns` — nothing else. **Adding a new step must never require adding a
field to `MapState`** — if a step's output needs to reach a renderer, that's a sign it
belongs in the existing fields (`objs`, `zones`, ...), not a reason to widen the schema.
Anything else a step produces goes through the `ProviderRegistry`, never onto `MapState`.

## `PlacementWorkspace` — the one shared, progressively-mutated object

`GameplayStep`/`VegetationStep`/`PickupStep`/`RepairStep` share a `PlacementWorkspace`
(created by whichever of the four runs first, via
`ctx.get_or_create(PlacementWorkspace, PlacementWorkspace)`, holding
`LevelWorkspace`/`ZoneWorkspace` per level/zone) that they mutate in place across the four
steps — `GameplayStep` populates `zw.occupied/gobjs/prot/...`, `VegetationStep` fills
`zw.open_set/blocked/passable`, `PickupStep` writes `zw.reach/used`. This is the SAME
registry mechanism as everything else (not a separate channel) — it's just the one case
where the published value is mutable and every later demander keeps mutating it, rather
than a value computed once and read thereafter.

This coupling is why `--stop-after` (below) is a prefix cut and not an arbitrary
skip-list: `PickupStep` reads `zw.open_set` assuming `VegetationStep` already populated
it. Skip `vegetation` and `PickupStep` sees the `ZoneWorkspace` dataclass defaults
(empty frozensets) instead of a real gap — a silent wrong-answer, not an error.

## `cli.py`'s fixed-preset vs. configurable split

`generate` is the only subcommand with CLI-selectable steps/overlays/renderers
(`--overlays` / `--renderers` / `--stop-after`, one of `GENERATE_STOP_POINTS`, a
**prefix cut**: run steps up to and including the named one, return early). `cli.py`
builds the `Pipeline` directly, by hand, in `_generate_steps()` — there is no separate
builder class; assembling a different step sequence is just a different list of
`add_step()` calls.

`render-ontology` stays outside this entire model — it renders the object taxonomy
itself (`renderers/ontology_render.py`), never touches a generated map, and `cli.py`
calls it directly with no `Pipeline` involvement.

## Adding a new step

1. New subpackage `steps/<name>/` — `step.py` with the class (+ any dataclasses it
   publishes), an **empty** `__init__.py` (the convention here: subpackage `__init__.py`s
   are empty; the *top-level* `steps/__init__.py` does all the re-exporting).
2. Register it in `steps/__init__.py`'s explicit import + `__all__` list — steps are not
   auto-discovered.
3. Wire it into `cli.py`'s `_generate_steps()` by hand, in the right position.
4. If its output must reach a renderer, thread it through `MapState`'s *existing* fields;
   don't add a new one. If it must reach a later step, publish a dataclass through the
   registry; don't add a ctx string key.

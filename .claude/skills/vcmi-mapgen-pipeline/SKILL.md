---
name: vcmi-mapgen-pipeline
description: "VCMI map-generator pipeline wiring: Pipeline and ProviderRegistry, the PipelineStep contract (constructor config, inject(ctx), run(catalog, map_state)), the frozen placement results, the additive add_objs rule, --stop-after, and the generate subcommand. Load before adding, changing or reordering a step, or touching core/pipeline.py or cli/."
metadata:
  generated_by: farrier
  source: library/skills/projects/vcmi-mapgen/vcmi-mapgen-pipeline/SKILL.md
  resolve: "farrier source .claude/skills/vcmi-mapgen-pipeline/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
  tags: [python, backend, standards, architecture]
---

# VCMI map-generator: pipeline and step wiring

The generator is one procedural pipeline. `cli/steps.py` builds it in `build_steps`, and
that list is the source of truth for which steps run and in what order. At the time of
writing it runs `terrain -> vegetation -> gameplay -> gated -> treasure ->
border -> portal -> loot -> scatter`.

Two hand-written files hold the rest of the contract. Read them before changing a step:

- `vcmi_mapgen/core/steps/AGENTS.md`: what a step must do, the additive rule, and how a step
  publishes a value for a later one.
- `vcmi_mapgen/core/model/AGENTS.md`: which data belongs on `MapState` and which belongs in
  the registry.

This skill covers how those pieces fit together. `vcmi-mapgen-maps` covers the domain.

## The step contract (`core.pipeline.PipelineStep`)

- **Constructor.** Config known before any step runs: seed, size, player count, the
  subterrain flag. Never a value another step produced.
- **`inject(self, ctx: ProviderRegistry) -> None`.** The step pulls the typed values it
  needs out of the registry and stores them on itself. `ctx.require(T)` raises
  `MissingProviderError` when no earlier step provided `T`. `ctx.get(T, T())` is for a
  producer that may not be in the pipeline. The base implementation is a no-op.
- **`run(self, catalog: Catalog, map_state: MapState) -> None`.** The step writes onto
  `map_state`. It passes `catalog` to every function that asks about an object. Every step must write onto it. Anything a later step needs goes out as a
  typed dataclass through `ctx.provide(...)`.

Each step's published values live in its `result.py`. A step may import another step's
`result` module, and nothing else from that step. `LootResult` sits in
`core/steps/loot/result.py`:

```python
@dataclass
class LootResult:
    pockets: Pockets = field(default_factory=dict)


class LootStep(PipelineStep):
    def __init__(self, priors: Priors, seed: int = 3, size: int = 72) -> None:
        self.priors = priors
        self.seed = seed
        self.size = size

    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx
        self._zones = ctx.require(ZoneIndex)
        self._guard_tiles = ctx.require(BorderResult).guard_tiles

    def run(self, catalog: Catalog, map_state: MapState) -> None:
        ...
        map_state.add_objs(self.objs)
        self._ctx.provide(LootResult(pockets=pockets_by_level))
```

`grep -n "provide(" vcmi_mapgen/core/steps/*/step.py` lists every value currently published.
Never key the registry by string. There is no `ctx["name"]` channel.

## `run` reads, calls and writes

`run` is the step's shell. It reads what it needs from `map_state` and from the values
`inject` pulled out of the registry. It calls functions that decide, and it writes their
results back. The decisions live in functions in the step's package. Those functions take
plain values and return plain values, so a test calls them with a few literal tiles and no
pipeline.

A loop inside `run` that chooses tiles, zones or objects is a function that has not been
moved out yet. Move it to the step's package before adding to it.
`run` stays under 30 lines. `vegetation/grow.py`, `scatter/piles.py` and `border/guard.py`
show the shape: a frozen value holding one level's inputs, and a function that returns one
level's result. `MapState.objs_by_level` gives each level's objects.

The `code-structure` skill's rules 1.7 and 1.8 cover the values those functions take. A
value a step receives from the registry is read, not written. A function takes the fields
it reads, not the whole zone map. `ZoneIndex.claims` and `ZoneIndex.targets`
break the first rule today, because later steps write into them. Do not add another field
of that kind.

## `Pipeline` sequences, it does not resolve

`Pipeline(catalog, size)` creates the `MapState` and one `ProviderRegistry`. `add_step`
appends a step, and `run()` calls `inject` then `run` on each step in the order it was
added. The registry changes how a value crosses between steps. It does not make the
pipeline a dependency graph, so a step never runs earlier because its inputs are ready.
Order matters for `MapState` writes, for `ZoneIndex` mutation and for RNG determinism.

## Placement steps hand each other frozen values

`VegetationStep` provides the `ZonePlan` (`core/planning/zone_plan.py`), each zone's
entrances, web and town room. It also provides `VegetationResult`, each zone's open and
walkable tiles. `GameplayStep` provides `GameplayResult`, one `PlacedZone` per zone.
`GatedStep` builds the `ZoneIndex` from those values, and `BorderStep` provides its guard
tiles in `BorderResult`. A producer provides a value once, and every consumer requires it.
No step creates a value for a later step to fill in.

`--stop-after` is a prefix cut and never a skip-list. A step whose producer was skipped
raises `MissingProviderError` when it requires the missing value.

## Every placement step is additive

A step appends its objects with `map_state.add_objs(new)`. It never removes or moves an
object an earlier step placed. It checks each candidate with a `CoverIndex` first, and it
treats a refusal as "try the next candidate". Terrain holds by construction: the step
draws identities from the catalog for the zone's terrain and keeps solid cells in the zone. Only `VegetationStep` may raise, when it walls off a pocket.
`core/steps/AGENTS.md` has the full rule, including guard spacing.

## Two subcommands build the pipeline

`cli/__main__.py` lists every subcommand in its docstring. `generate` and
`render-vegetation` are the only ones that build the pipeline. `generate` alone takes
`--renderers` and `--stop-after`. `render-vegetation` always stops after `vegetation` and
writes one terrain-and-vegetation PNG per seed and level to `out/render/vegetation/`. Both
take `--vegetation`, which picks a sampler from `SAMPLERS` in `cli/steps.py`. A second
algorithm for part of a step is a variant of a role the step takes in its constructor, as
`VegetationStep` takes a `Sampler`. The step stays one class and publishes the same values,
so the later steps never know which variant ran. Never subclass a step to swap an
algorithm. `render-ontology` renders the object catalog through
`renderers/ontology_render.py`. It builds no pipeline and never touches a generated map.

After `pipeline.run()`, `cli/generate.py` reads results back from `pipeline.ctx` by type,
for example `pipeline.ctx.get(LootResult, LootResult())`.

## Adding a step

1. Create `core/steps/<name>/` with `step.py`, `result.py` when it publishes a value, and
   an empty `__init__.py`. Every subpackage `__init__.py` is empty. The top-level
   `core/steps/__init__.py` does the re-exporting.
2. Add the class to the imports and `__all__` in `core/steps/__init__.py`. Steps are not
   auto-discovered.
3. Add its name to `GENERATE_STOP_POINTS` and its construction to `build_steps` in
   `cli/steps.py`, in both cases at its position in the run order. A step that reads
   corpus statistics takes `priors: Priors` first. `build_steps` passes it the one value
   the CLI loaded with `corpus.priors.load_priors`, and no step loads a file itself.
4. Publish anything a later step needs as a typed dataclass in the step's `result.py`.
   Do not add a field to `MapState` so that a renderer can read it. The test in
   `core/model/AGENTS.md` decides that.

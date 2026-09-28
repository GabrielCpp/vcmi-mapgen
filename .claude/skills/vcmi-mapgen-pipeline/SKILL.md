---
name: vcmi-mapgen-pipeline
description: "VCMI map-generator pipeline wiring: Pipeline and ProviderRegistry, the PipelineStep contract (constructor config, inject(ctx), run(catalog, map_state)), the shared PlacementWorkspace, the additive add_objs rule, --stop-after, and the two cli.py subcommands. Load before adding, changing or reordering a step, or touching pipeline.py or cli.py."
metadata:
  generated_by: farrier
  source: library/skills/projects/vcmi-mapgen/vcmi-mapgen-pipeline/SKILL.md
  resolve: "farrier source .claude/skills/vcmi-mapgen-pipeline/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
  tags: [python, backend, standards, architecture]
---

# VCMI map-generator: pipeline and step wiring

The generator is one procedural pipeline. `cli.py` builds it in `_generate_steps`, and
that list is the source of truth for which steps run and in what order. At the time of
writing it runs `terrain -> segment -> vegetation -> gameplay -> gated -> treasure ->
border -> portal -> loot -> scatter`.

Two hand-written files hold the rest of the contract. Read them before changing a step:

- `vcmi_mapgen/steps/AGENTS.md`: what a step must do, the additive rule, and how a step
  publishes a value for a later one.
- `vcmi_mapgen/models/AGENTS.md`: which data belongs on `MapState` and which belongs in
  the registry.

This skill covers how those pieces fit together. `vcmi-mapgen-maps` covers the domain.

## The step contract (`pipeline.PipelineStep`)

- **Constructor.** Config known before any step runs: seed, size, player count, the
  subterrain flag. Never a value another step produced.
- **`inject(self, ctx: ProviderRegistry) -> None`.** The step pulls the typed values it
  needs out of the registry and stores them on itself. `ctx.require(T)` raises
  `MissingProviderError` when no earlier step provided `T`. `ctx.get(T, T())` is for a
  producer that may not be in the pipeline. The base implementation is a no-op.
- **`run(self, catalog: Catalog, map_state: MapState) -> None`.** The step writes onto
  `map_state`. It passes `catalog` to every function that asks about an object. Every step must write onto it. Anything a later step needs goes out as a
  typed dataclass through `ctx.provide(...)`.

```python
@dataclass
class LootResult:
    pockets: Pockets = field(default_factory=dict)


class LootStep(PipelineStep):
    def __init__(self, seed: int = 3, size: int = 72) -> None:
        self.seed = seed
        self.size = size

    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx
        self._zones = ctx.require(ZoneIndex)
        self._workspace = ctx.require(PlacementWorkspace)

    def run(self, catalog: Catalog, map_state: MapState) -> None:
        ...
        map_state.add_objs(self.objs, TerrainGate(catalog))
        self._ctx.provide(LootResult(pockets=pockets_by_level))
```

`grep -n "provide(" vcmi_mapgen/steps/*/step.py` lists every value currently published.
Never key the registry by string. There is no `ctx["name"]` channel.

## `run` reads, calls and writes

`run` is the step's shell. It reads what it needs from `map_state` and from the values
`inject` pulled out of the registry. It calls functions that decide, and it writes their
results back. The decisions live in functions in the step's package. Those functions take
plain values and return plain values, so a test calls them with a few literal tiles and no
pipeline.

A loop inside `run` that chooses tiles, zones or objects is a function that has not been
moved out yet. Move it to the step's package before adding to it.

The `code-structure` skill's rules 1.7 and 1.8 cover the values those functions take. A
value a step receives from the registry is read, not written. A function takes the fields
it reads, not the whole workspace or zone map. `ZoneRecord.used` and `PlacementWorkspace`
break the first rule today, because later steps write into them. Do not add another field
of that kind.

## `Pipeline` sequences, it does not resolve

`Pipeline(catalog, size)` creates the `MapState` and one `ProviderRegistry`. `add_step`
appends a step, and `run()` calls `inject` then `run` on each step in the order it was
added. The registry changes how a value crosses between steps. It does not make the
pipeline a dependency graph, so a step never runs earlier because its inputs are ready.
Order matters for `MapState` writes, for workspace mutation and for RNG determinism.

## `PlacementWorkspace`: the one shared mutable object

The placement steps collaborate through one `PlacementWorkspace` in `pipeline.py`. It
holds a `LevelWorkspace` per level and a `ZoneWorkspace` per zone. The first step that
demands it creates it with `ctx.get_or_create(PlacementWorkspace, PlacementWorkspace)`.
Every later placement step mutates that same instance in place. The field comments in
`ZoneWorkspace` and `LevelWorkspace` name the step that sets each field.

Do not add a second object like this. A new cross-step value is a typed dataclass on the
registry. A new field on `ZoneWorkspace` is justified only when an existing placement
step must read what an earlier placement step decided.

This coupling is why `--stop-after` is a prefix cut and never a skip-list. `GatedStep`
reads `zw.open_set` on the assumption that `VegetationStep` filled it. Skip vegetation
and `GatedStep` reads the empty frozenset default. That gives a wrong map, not an error.

## Every placement step is additive

A step appends its objects with `map_state.add_objs(new, rules)`, where `rules` is a
`PlacementRules` such as `TerrainGate(catalog)`. It never removes or moves an object
an earlier step placed. It checks each candidate with a `CoverIndex` and the terrain
rules first, and it treats a refusal as "try the next candidate". Only `VegetationStep` may raise, when it walls off a pocket.
`steps/AGENTS.md` has the full rule, including guard spacing.

## `cli.py` has two subcommands

- `generate` builds the pipeline. It is the only subcommand that takes `--overlays`,
  `--renderers` and `--stop-after`. Keep that configurability on `generate` alone.
- `render-ontology` renders the object catalog through `renderers/ontology_render.py`.
  It builds no pipeline and never touches a generated map.

After `pipeline.run()`, `cmd_generate` reads results back from `pipeline.ctx` by type,
for example `pipeline.ctx.get(LootResult, LootResult())`.

## Adding a step

1. Create `steps/<name>/` with `step.py` and an empty `__init__.py`. Every subpackage
   `__init__.py` is empty. The top-level `steps/__init__.py` does the re-exporting.
2. Add the class to the imports and `__all__` in `steps/__init__.py`. Steps are not
   auto-discovered.
3. Add its name to `GENERATE_STOP_POINTS` and its construction to `_generate_steps` in
   `cli.py`, in both cases at its position in the run order.
4. Publish anything a later step needs as a typed dataclass defined next to the step.
   Do not add a field to `MapState` so that a renderer can read it. The test in
   `models/AGENTS.md` decides that.

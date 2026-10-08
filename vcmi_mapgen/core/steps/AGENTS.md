# core/steps/ — the PipelineStep contract

One subpackage per step (`terrain_gen/`, `segment/`, `vegetation/`, `gameplay/`,
`gated/`, `treasure/`, `portal/`, `loot/`, `sets/`, `scatter/`, `roads/`), each holding a `step.py` with one `PipelineStep` subclass. `VegetationStep` first calls `core/planning/zone_plan.py`, which builds each zone's entrances, walkable web and the sea plan. See
`vcmi-mapgen-pipeline` for `PipelineStep`/`Pipeline`/`ProviderRegistry` themselves
(in `core/pipeline.py`); this file is the contract a new or changed step must satisfy.

## Map

- `terrain_gen/`: `TerrainStep`, the terrain of both levels drawn by the `TerrainModel` it is given, and its place map split into territories joined by one-tile doors. `cli/steps.py` gives it the places model, the only one.
- `vegetation/`: `VegetationStep`, the corpus-fitted trees, rocks and lakes, grown zone by zone by the `Sampler` it is given. `cli/steps.py` `SAMPLERS` names the Gibbs and the field samplers. It also plans each place's content with the `ContentPlanner` it is given, `HopContent` by default, and provides the `ContentPlan` that gameplay and loot read. Once the trees stand it chooses the loot zones with `core/planning/loot_zones.py` `choose_loot_zones` and provides `LootZones`: the doors step leaves their doors open, gameplay places nothing in them and the gated step seals them.
- `gameplay/`: `GameplayStep`, the player zones, sea objects, gates, towns, mines, shipyards, dwellings, banks and visitables.
- `gated/`: `GatedStep`, which seals small one-passage zones behind a Border Gate or a monolith pair.
- `treasure/`: `TreasureStep`, the treasure inside each sealed loot zone and on each island, priced by its effort in hero-days. It provides `TreasureResult`.
- `portal/`: `PortalStep`, the portal pairs that link cut-off zones to the start zone, and each portal place's prizes priced by its effort. It provides `PortalResult`.
- `loot/`: `LootStep`, the seer-hut quests and the pocket caches, guarded only in a deep pocket.
- `sets/`: `SetsStep`, the combined artifact sets. The treasure, portal and loot steps each hold one prize slot open per place, and this step deals whole sets onto the slots in the top two effort bands, then fills every other slot. It provides `SetsResult`.
- `scatter/`: `ScatterStep`, the free resource piles placed last.
- `roads/`: `RoadsStep`, the last step. It lays each level's roads into `map_state.roads` with the `RoadLayer` it is given, `PassageRoads` from `cli/steps.py`. It runs after every object, so it routes over the tiles no blocking cell or gate covers and no later object can stand on a road. A lasting object's visit tile is a blocking entrance, so no road runs over it.

## What a step must do

**A step exists to advance the map. Every step's `run()` must write onto `map_state`.**
That is the whole test — not "does this step do something," but "does this step make
the map itself different." A step that only computes a value for the next step in line
is not a step; it is either part of the step that actually needs the value (merge it in)
or the value itself, expressed as a plain function/dataclass another step's `run()` calls
directly.

There are **no ctx-only steps** — no exceptions. If you find yourself writing a
`PipelineStep` subclass whose `run()` never touches `map_state`, that is not a new kind
of step, it is a sign one of two things happened:

1. **An artificial split.** The value has exactly one consumer, and that consumer is the
   very next step in the list. This is what `TerrainGenStep`/`TileStep` used to be:
   `TerrainGenStep` generated a raw macro-topology grid and published it into the shared
   registry; `TileStep`, run immediately after, was its only reader, and immediately
   superseded the value with its own post-despeckle version. Splitting macro-generation
   from despeckle into two `PipelineStep`s bought nothing — it just added a
   registry round-trip between two halves of one job. They are now one step
   (`TerrainStep`, in `steps/terrain_gen/step.py`), and the raw grid never leaves it.
   **Fix:** merge the two steps.
2. **A genuinely shared, cross-step value with no map-level meaning of its own** — e.g.
   `TerrainGrids` (the tunnel-protect corridor cells, needed by
   `VegetationStep`) or `ZonePlan` (each zone's entrances and web, which
   `VegetationStep` computes and the later placement steps read). This data is real and does need
   to cross steps — but the step that *computes* it also has real map-level work to do
   (`TerrainStep` writes `map_state.terrain`; `VegetationStep` writes
   `map_state.objs`), so it is published as a side effect of an
   already-legitimate step's `run()`, never as the sole reason a step exists.

## `run` reads, calls and writes

A step's `run()` reads its inputs, calls the functions in its package that decide, and
writes their results. It stays under 30 lines. A loop that chooses tiles, zones or objects
lives in the step's package as a function over plain values, with its own test, as
`vegetation/grow.py` and `scatter/piles.py` do. A step that works level
by level gets each level's objects from `MapState.objs_by_level`.

## A step receives its priors in its constructor

A step that reads corpus statistics takes `priors: Priors` (`core/priors/bundle.py`) as
its first constructor argument and passes on only the fields each function reads. No
module under `core/` loads a file from `data/pp`. `cli/steps.py` builds every step from
the one `Priors` value `corpus.priors.load_priors` returns, and a test takes the session
`priors` fixture from `vcmi_mapgen/conftest.py` or builds a small value of its own.

## A step learns about objects through its catalog

`run(self, catalog: Catalog, map_state: MapState)` receives the one `Catalog`
(`core/catalog.py`). The step passes it as the first argument to every function that
asks about an object: identity, footprint, terrain coupling, candidates, decoration,
mines or spells. No module under `core/` imports `vcmi.catalog`. A test can hand a step a
small fake catalog, as `scatter/step_test.py` does.

A test that runs two steps together sits in `core/steps/` itself, as `gameplay_step_test.py`
and `water_test.py` do, because no step package may import another step.

## Every placement step is additive

A step appends its own objects with `map_state.add_objs(new)`. It never removes,
moves or replaces an object an earlier step placed. Plan into a scratch list and commit only what fits: pre-check
each object with `CoverIndex.try_claim`, and try the next candidate when one is refused.
A step draws each identity from the catalog for its zone's terrain, but a zone may hold
tiles of another terrain: the places model paints accents and transitions inside a zone. So
every solid cell is also checked against its own tile's terrain with
`core.placement.ground.stands` before the object is kept. A group that fails part way rolls the cover back to its `mark()`. Only `VegetationStep` may raise, when it walls off a pocket.

The step that places a guarded object also places its monster. No guard stands within
Chebyshev 2 of another (`core.placement.guards.guard_spaced`), so no later pass deletes
duplicate guards.

Every guard has a ward, the thing it protects: a reward, a mine, a dwelling, a bank, a town,
a visitable, or a passage into a place that holds one. The step decides the ward before it
places the guard, and a guard with no ward is never placed.

## How a step publishes a value for a later step

Never a raw string-keyed `ctx["key"] = value` entry. Instead:

1. Define a `@dataclass` for the value in the producing step's `result.py` (e.g.
   `GateResult` in `gameplay/result.py`, `GatedResult` in `gated/result.py`). A step may
   import another step's `result` module, and nothing else from that step.
2. The producing step's `run()` calls `self._ctx.provide(SomeResult(...))` once it has
   computed the value (`self._ctx` is whatever `inject()` was given — store it there).
3. A later step's `inject()` reads it back:
   - `ctx.require(SomeResult)` when the producing step is guaranteed to have already run
     (raises `MissingProviderError` otherwise — that always means the steps were wired in
     the wrong order, never something to work around).
   - `ctx.get(SomeResult, SomeResult())` when the producing step might not be in the
     pipeline at all (e.g. the CLI reads `TownsIndex`'s empty default when a
     `--stop-after` run ends before `GameplayStep` published them).

A value is provided once, by the one step that produces it. No step creates a value for a
later step to fill in.

This is the entire contract: type-keyed, memoized-per-run, no string keys, no step that
exists solely to populate one. `MapState` vs. registry placement follows
`vcmi_mapgen/core/model/AGENTS.md`'s test (is this a fact the map itself carries, or
disposable analysis computed once from it) — the registry is always disposable analysis
by construction, since anything map-level went onto `MapState` in the same `run()` call.

## Step sequencing is unchanged

None of this touches *when* steps run. `add_step()` order is still hand-written and still
matters — `MapState`/`ZoneIndex` mutation order and RNG determinism depend on it
exactly as before. The registry only changes how a value crosses from one already-ordered
step to a later one; it is not a dependency graph, and adding a value to it never lets a
step run earlier or later than its position in the list says it does.

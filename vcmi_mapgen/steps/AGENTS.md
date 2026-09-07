# steps/ — the PipelineStep contract

One subpackage per step (`terrain_gen/`, `segment/`, `gate/`, `gameplay/`, `vegetation/`,
`pickup/`, `repair/`), each holding a `step.py` with one `PipelineStep` subclass. See
`vcmi-mapgen-pipeline` for `PipelineStep`/`Pipeline`/`ProviderRegistry` themselves
(in `pipeline.py`); this file is the contract a new or changed step must satisfy.

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
   from autotiling into two `PipelineStep`s bought nothing — it just added a
   registry round-trip between two halves of one job. They are now one step
   (`TerrainStep`, in `steps/terrain_gen/step.py`), and the raw grid never leaves it.
   **Fix:** merge the two steps.
2. **A genuinely shared, cross-step value with no map-level meaning of its own** — e.g.
   `TerrainGrids` (post-despeckle terrain-code grids + tunnel-protect corridor cells,
   needed by `SegmentStep`/`GameplayStep`/`RepairStep`) or `PlacementWorkspace` (the
   `Gameplay→Vegetation→Pickup→Repair` shared workspace). This data is real and does need
   to cross steps — but the step that *computes* it also has real map-level work to do
   (`TerrainStep` writes `map_state.cells`/`surfs`; `GameplayStep` writes
   `map_state.objs`/`player_towns`), so it is published as a side effect of an
   already-legitimate step's `run()`, never as the sole reason a step exists.

## How a step publishes a value for a later step

Never a raw string-keyed `ctx["key"] = value` entry. Instead:

1. Define a `@dataclass` for the value, next to the step that produces it (e.g.
   `GateResult` in `steps/gate/step.py`, `PickupIndex` in `steps/pickup/step.py`).
2. The producing step's `run()` calls `self._ctx.provide(SomeResult(...))` once it has
   computed the value (`self._ctx` is whatever `inject()` was given — store it there).
3. A later step's `inject()` reads it back:
   - `ctx.require(SomeResult)` when the producing step is guaranteed to have already run
     (raises `MissingProviderError` otherwise — that always means the steps were wired in
     the wrong order, never something to work around).
   - `ctx.get(SomeResult, SomeResult())` when the producing step might not be in the
     pipeline at all (e.g. `GateStep` only runs for subterrain maps — `GameplayStep`/
     `PickupStep`/`RepairStep` read `GateResult`'s empty default instead of erroring).
   - `ctx.get_or_create(SomeType, SomeType)` for the one shape where the *first* demander
     creates the value and every later demander mutates that SAME instance further
     (`PlacementWorkspace`: `GameplayStep` creates it, `VegetationStep`/`PickupStep`/
     `RepairStep` each mutate it in place).

This is the entire contract: type-keyed, memoized-per-run, no string keys, no step that
exists solely to populate one. `MapState` vs. registry placement follows
`vcmi_mapgen/models/AGENTS.md`'s test (is this a fact the map itself carries, or
disposable analysis computed once from it) — the registry is always disposable analysis
by construction, since anything map-level went onto `MapState` in the same `run()` call.

## Step sequencing is unchanged

None of this touches *when* steps run. `add_step()` order is still hand-written and still
matters — `MapState`/`PlacementWorkspace` mutation order and RNG determinism depend on it
exactly as before. The registry only changes how a value crosses from one already-ordered
step to a later one; it is not a dependency graph, and adding a value to it never lets a
step run earlier or later than its position in the list says it does.

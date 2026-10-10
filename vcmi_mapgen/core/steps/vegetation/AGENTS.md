# core/steps/vegetation/

## Map

- `border_plan.py`: the zone-border plan that closes open crossings outside the entrance bands.
  It reads the zone owners and the closing pairs from `core/planning/borders.py`, so an open
  pair stays walkable. A web tile is sealed only when its open neighbours stay joined inside
  its own zone.
- `canvas.py`: `ZoneCanvas`, the zone grids every sampler grows on. It owns the hard rules:
  `blocked_cells` is the legality check, which also refuses a blocking cell on a tile whose
  terrain the identity's `VegModel.iland` lacks, and `try_place` and `try_remove` refuse any move that
  walls off open ground. `zone_rng` seeds one zone's draws.
- `connect.py`: `keeps_connected` and `frees_connected`, the compiled connectivity checks
  behind `try_place` and `try_remove`.
- `field/`: `FieldSampler`, the default sampler, which covers a cellular field's blocked mask with decorations.
  `cellular.py` draws the field and the per-edge-bin coverage that shapes the mask.
  `sampler.py` tries `FILL_TRIES` placements per uncovered tile and checks the best
  `FILL_CHECKS` with the canvas.
- `gibbs/`: `GibbsSampler`, the marked-point-process sampler fitted to `VegetationStats` from
  `core/priors/vegetation.py`. Births and deaths go through the canvas. `energy.py` holds the
  compiled local interaction energy.
- `grow.py`: `grow_level`, one level's vegetation grown zone by zone with the `Sampler` it is
  given, and `vegetation_models`, one fitted model per terrain.
- `mix.py`: `ZoneMix`, a zone's corpus-expected category counts and the category and identity
  draws both samplers make from them.
- `model.py`: `VegModel`, the per-terrain model both samplers read, and `build_model`. `RINT`
  is the local interaction range in Chebyshev rings. `BASE_W` is the weight every native
  identity gets on top of its corpus frequency, so a sprite the corpus rarely uses can still
  appear.
- `sampler.py`: the `Sampler` role that `grow_level` calls, with `SampleOptions`, one zone's
  brief, and `ZoneGrowth`, what a sampler returns. It imports no sampler.
  `render-vegetation --vegetation gibbs` and `generate --vegetation gibbs` select the Gibbs
  sampler through `cli/steps.py` `SAMPLERS`.
- `result.py`: `VegetationResult`, which `VegetationStep` publishes.
- `step.py`: `VegetationStep`, which takes its `Sampler` and its `ContentPlanner` in the constructor. It plans the content first, picks the plan's homes as the player zones, and provides the `ContentPlan` beside the `ZonePlan`.

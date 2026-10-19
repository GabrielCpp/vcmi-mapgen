# core/steps/vegetation/

## Map

- `border_plan.py`: the zone-border plan that closes open crossings outside the entrance bands.
  It reads the zone owners and the closing pairs from `core/planning/borders.py`, so an open
  pair stays walkable. A web tile is sealed only when its open neighbours stay joined inside
  its own zone and no open tile of either zone is shut away. Any other cell stays open when
  sealing it would shut a web tile away from the rest of the web. A closed tile takes a larger
  piece when its other blocking cells fall on tiles already blocked.
- `canvas.py`: `ZoneCanvas`, the zone grids every sampler grows on, in a window of the zone's
  box grown by its largest decoration's reach plus one. It owns the hard rules:
  `blocked_cells` is the legality check, which also refuses a solid cell on a tile whose
  terrain the identity's `VegModel.iland` lacks, and `try_place` and `try_remove` refuse any
  move that walls off open ground of any zone in the window. `zone_rng` seeds one zone's
  draws.
- `connect.py`: `keeps_connected` and `frees_connected`, the compiled connectivity checks
  behind `try_place` and `try_remove`.
- `field/`: `FieldSampler`, the default sampler, which covers a cellular field's blocked mask with decorations.
  `cellular.py` draws a Worley field from blue-noise seeds and the per-edge-bin coverage that shapes the mask. The mask blocks the tiles nearest the Voronoi edges, so walls close around rooms in the cells, and the canvas's connectivity rule leaves each room an opening.
  `sampler.py` fills the forced tiles first, from the zone edge inward, then the rest. It
  tries `FILL_TRIES` identities per uncovered tile, each at its first legal position over
  that tile, and checks the best `FILL_CHECKS` with the canvas.
- `gibbs/`: `GibbsSampler`, the marked-point-process sampler fitted to `VegetationStats` from
  `core/priors/vegetation.py`. Births and deaths go through the canvas. `energy.py` holds the
  compiled local interaction energy.
- `grow.py`: `grow_level`, one level's vegetation grown zone by zone with the `Sampler` it is
  given, and `vegetation_models`, one fitted model per terrain. Each zone's brief holds the
  whole level's web and land, walled by the towns and by what earlier zones grew. Its forced
  border is the zone's rim and wall share, less the entrance bands.
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
- `step.py`: `VegetationStep`, which takes its `Sampler` and its `ContentPlanner` in the constructor. It plans the content first, picks the plan's homes as the player zones, and provides the `ContentPlan` beside the `ZonePlan`. It hands the zone plan each level's wall widths and the tiles the map keeps open: doors, gate rooms and approaches, and tunnels on level 1.

# core/steps/vegetation/

## Map

- `border_plan.py`: the zone-border plan that closes open crossings outside the entrance bands.
  It reads the zone owners and the crossing pairs from `core/planning/borders.py`.
- `sample.py`: the marked-point-process sampler that grows one zone's decoration, fitted to
  `VegetationStats` from `core/priors/vegetation.py`.
- `result.py`: `VegetationResult`, which `VegetationStep` publishes.
- `step.py`: `VegetationStep`.

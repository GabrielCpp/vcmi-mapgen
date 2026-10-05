# core/steps/gated/

## Map

- `loot_zones.py`: `mark_loot_zones` and `walk_targets`, what gating changes in a level's zone records and walk targets.
- `placer.py`: `place_gated_zones`, which seals a small one-passage zone behind a Border Gate and its Keymaster, or a monolith pair. A loot zone and the partner outside it stand only in zones a home reaches on foot.
- `result.py`: `GatedResult`, which `GatedStep` publishes.
- `step.py`: `GatedStep`.

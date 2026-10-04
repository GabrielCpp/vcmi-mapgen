# core/steps/loot/

## Map

- `pickups.py`: the pocket caches. Under a `PocketPlan` every pocket is filled, a deep
  pocket where a guard fits gets one over an artifact or a Pandora's box, and
  every other pocket gets resource piles or chests. Without a plan every filled pocket
  takes a guard, as markov maps do.
- `pocket_plan.py`: the pure pocket decisions: shallow or deep, each place's mean guard level,
  the ward's artifact tier and the guard level its value earns.
- `pockets.py`: the pocket guard tile, the approach tiles no pocket may hold, and the
  town-to-mine routes a pocket guard must not cut. Pocket detection and dedupe live in
  `core/grid/pockets.py`.
- `quests.py`: the seer-hut quests, each linking an artifact to the hut that asks for it.
- `result.py`: `LootResult`, which carries the pockets `LootStep` publishes.
- `step.py`: `LootStep`.

# core/steps/loot/

## Map

- `pickups.py`: the guarded pocket caches, a one-tile guard on each mask G and loot inside.
- `pockets.py`: the pocket guard tile, the approach tiles no pocket may hold, and the
  town-to-mine routes a pocket guard must not cut. Pocket detection and dedupe live in
  `core/grid/pockets.py`.
- `quests.py`: the seer-hut quests, each linking an artifact to the hut that asks for it.
- `result.py`: `LootResult`, which carries the pockets `LootStep` publishes.
- `step.py`: `LootStep`.

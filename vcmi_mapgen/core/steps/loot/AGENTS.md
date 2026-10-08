# core/steps/loot/

## Map

- `pickups.py`: the pocket caches. Under a `PocketPlan` every pocket is filled, a deep
  pocket where a guard fits gets one over an artifact or a Pandora's box, and
  every other pocket gets resource piles or chests. A guarded pocket's artifact tile is held open as a prize slot for `SetsStep`. Without a plan every filled pocket
  takes a guard.
- `pocket_plan.py`: the pure pocket decisions: shallow or deep, which places the plan
  covers, and the ward's artifact tier its guard level earns. The guard level itself comes
  from `core/planning/guarding.py`.
- `pockets.py`: the pocket guard tile, the approach tiles no pocket may hold, and the
  town-to-mine routes a pocket guard must not cut. Pocket detection and dedupe live in
  `core/grid/pockets.py`.
- `quests.py`: the seer-hut quests, each linking an artifact to the hut that asks for it. No quest asks for a set part or a combined artifact.
- `result.py`: `LootResult`, which carries the pockets and the held prize slots `LootStep` publishes.
- `step.py`: `LootStep`.

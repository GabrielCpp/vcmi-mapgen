# core/steps/compensation/

The fairness pass of `docs/design/compensation.md`. It runs after every reward stands and
before the roads.

## Map

- `prize.py`: the pure decisions. `BAR` holds the corpus median share of the best player's
  claimed value at 20 and 40 hero-days. `deficits` gives the gold each player lacks to meet
  it, `prize_tier` the cheapest artifact tier worth that gold, and `prize_ground` the tiles
  a player reaches strictly before every other player within a horizon.
- `stand.py`: `PrizeStand` stands the artifact and its guard, most open tile first. A guard
  stands only where `EffortMap.detour` says it adds less than `DETOUR` days to any player's
  way to any tile, so a prize never cuts off or delays the rest of the map.
- `step.py`: `CompensationStep`. It serves the players who lack the most first, each with
  one prize, at 20 days where one fits, else at 40.
- `result.py`: `Prize` and `CompensationResult`, the claimed value before the prizes and the
  players still behind after them.

`cli/compensation_test.py` runs the pipeline on a small four-player map and checks the
prizes against a fresh reading of the finished map.

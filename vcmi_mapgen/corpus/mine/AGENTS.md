# corpus/mine/

The miners: each reads the corpus maps and returns one prior value from `core/priors/`.

## Map

- `gameplay.py`: `mine_gameplay`, the per-terrain gameplay densities, mixes and mine ratios.
- `gates.py`: `mine_gate_stats`, the Subterranean Gate counts and spacing.
- `macro.py`: `mine_macro`, the zone areas, terrain shares, terrain adjacency and barrier fraction per level.
- `markov.py`: `learn` and `learn4`, the raster and four-neighbour terrain Markov chains per level.
- `vegetation.py`: `mine`, the per-terrain decoration intensity, pair correlation and
  coverage. `--report TERRAIN` prints one terrain's tables.

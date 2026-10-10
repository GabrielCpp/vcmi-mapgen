# corpus/mine/

The miners: each reads the corpus maps and returns one prior value from `core/priors/`.

## Map

- `effort.py`: `mine_effort`, the band edges and the per-class effort medians, read from the hero-days at each corpus artifact pickup.
- `gameplay.py`: `mine_gameplay`, the per-terrain gameplay densities, mixes and mine ratios.
- `gates.py`: `mine_gate_stats`, the Subterranean Gate counts and spacing.
- `macro.py`: `mine_macro`, the zone areas, terrain shares, terrain adjacency and barrier fraction per level.
- `markov.py`: `learn` and `learn4`, the raster and four-neighbour terrain Markov chains per level, and `learn_inside`, the four-neighbour chain counted only inside one place.
- `mines.py`: `mine_curve`, the resource mine curve fitted in log space over each corpus map's land area and player count, with the intercept raised by half the residual variance.
- `places.py`: `mine_places`, the place, palette, paint and content statistics per level from `core/reading` place inference and paint readings, `place_labels`, each map's place label grid, and `map_players`, each town's owner read from the map's `.h3m`, because the corpus `.vmap` files carry no owner. The content statistics are one `core/reading/content.py` `PlaceContent` row per inferred place of a map that has a home, its hop count read over the walkable place adjacency. The road statistics are one `core/reading/roads.py` reading per level, pooled by `pool_roads`.
- `territories.py`: `mine_territories`, one level's territory spread pooled over the corpus maps from `core/reading/territories.py`: zones per player and per neutral territory, doors per territory pair, and each map's own door levels on a player's border and between neutral territories.
- `tiler.py`: `learn`, the frame and flip real maps draw per terrain and neighbour terrains, and the road frame and flip per road-neighbour mask, read from each `.vmap`'s tile strings.
- `vegetation.py`: `mine`, the per-terrain decoration intensity, pair correlation and
  coverage. `--report TERRAIN` prints one terrain's tables.

# core/grid/

Pure algorithms over tile sets and terrain grids. A module here takes tiles, cells or
arrays and returns plain values. It knows nothing about steps or the
registry.

## Map

- `components.py`: 4-connected components of a tile set, and `open_islands`, the open ground walled off from every anchor.
- `detour.py`: `detours`, whether closing a few tiles parts open tiles beside them that joined through them, within `MARGIN` tiles, so a hero must go the long way round.
- `flanks.py`: `flank_tiles`, the tile left and the tile right of each row of a sprite, and `closed_flanks`, how many of the two sides hold a closed tile.
- `geometry.py`: the 4- and 8-neighbourhoods, edge distance, the open run-length statistic
  and `centre_key`, the nearest-to-a-point sort key.
- `noise.py`: the seeded value-noise field.
- `paths.py`: `geodesic_path` inside a tile set, `farthest_points` sampling and the backbone `SPACING`.
- `pocket_masks.py`: `parse_masks`, which reads the drawn pocket shapes of `data/pockets.txt` into every distinct rotation and mirror.
- `pockets.py`: `find_pockets`, which slides those masks over the walkable tiles with the map edge read as wall, `find_rooms`, which takes every dead end of at most 16 tiles behind a one-tile mouth whatever its shape, each pocket tile's depth from its guard, `dedupe_pockets`, and the `Pockets` type.
- `splits.py`: `splits`, whether closing a few tiles leaves two or more open pieces of at least a given size beside them, the way a guard's zone of control parts one territory into two.
- `snug.py`: `snug`, whether a sprite sits snug for its size class: a one-tile body in a hole or a corner, a two-tile body with the tile past its far end closed, a larger body with a closed tile above its top. `sided` asks whether a closed tile stands beside the body. A corner contact alone never counts. `size_class` gives the class and `solid_cells` the body cells.
- `reach.py`: the one BFS family over tile sets: `distances`, `reach` and `walk`, with
  `STEPS4` and `STEPS8`, `entry_reach` from one entry tile, and `land_reach`, the land
  tiles a hero walks to from the start over every level and through open gates. A search with its own stop
  rule, or one over a label grid or a numpy array, keeps its own loop.
- `segment.py`: `segment_level`, the terrain flood fill with each tile's position inside its zone, `flood_label`, the bare flood fill, and `zones_of_labels`, the zones of a finished label grid.

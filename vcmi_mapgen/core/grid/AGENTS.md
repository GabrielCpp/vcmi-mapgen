# core/grid/

Pure algorithms over tile sets and terrain grids. A module here takes tiles, cells or
arrays and returns plain values. It knows nothing about steps, the registry or the
workspace.

## Map

- `components.py`: 4-connected components of a tile set, and `open_islands`, the open ground walled off from every anchor.
- `geometry.py`: the 4- and 8-neighbourhoods, edge distance and the open run-length statistic.
- `noise.py`: the seeded value-noise field.
- `paths.py`: `geodesic_path` inside a tile set, `farthest_points` sampling and the backbone `SPACING`.
- `pockets.py`: pocket detection, each pocket's mouth, and each pocket tile's depth from its mouth.
- `segment.py`: `segment_level`, the terrain flood fill with each tile's position inside its zone.

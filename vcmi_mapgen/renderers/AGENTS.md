# renderers/: outputs drawn from a finished map

Each renderer takes a finished `MapState` and writes a picture or a map file. None of them changes the map.

## Map

- `ontology_render.py`: the `render-ontology` output, one PNG per leaf of the object catalog.
- `overlays/`: semi-transparent debug layers drawn over a PNG render: zones, blocking, guards, passages, pockets and tile types.
- `palette.py`: the terrain colours and tile size the schematic renders and the overlays share, keyed by `Terrain`.
- `png.py`: `PngRenderer`, which draws each level with the real H3 sprites.
- `sprites.py`: the sprite compositor. It pastes terrain tiles and object sprites from the LOD in painter's order.
- `vmap.py`: `VmapRenderer`, which calls `vcmi/export.py`, `vcmi/players.py` and the `.vmap` writer.

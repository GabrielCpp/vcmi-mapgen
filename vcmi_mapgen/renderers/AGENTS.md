# renderers/: outputs drawn from a finished map

Each renderer takes a finished `MapState` and writes a picture or a map file. None of them changes the map.

## Map

- `ontology_render.py`: the `render-ontology` output, one PNG per leaf of the object catalog.
- `overlays/`: semi-transparent debug layers drawn over a PNG render: zones, blocking, guards, passages, pockets, inferred places and tile types.
- `palette.py`: the terrain colours and tile size the schematic renders and the overlays share, keyed by `Terrain`.
- `png.py`: `PngRenderer`, which draws each level with the real H3 sprites. It reads them through any `ContentArchive`, so a `SpriteSource` adds the enabled mods' sprites. A caller may hand `render` the level's tile strings to draw instead of re-tiling the map.
- `sprites.py`: the sprite compositor. It pastes terrain tiles, road tiles and object sprites from a `ContentArchive` in painter's order. A sprite with no `.def` loads from a VCMI `.json` animation and its `.png` frames, as the HotA highlands and wasteland tiles do.
- `territories.py`: `render_territories`, the territory view `generate` writes as `territories.png` and, with an underground, `territories_underground.png`. It takes a level's place label, the territory of each place, the owner of each territory, the door tiles and the home town tiles, and draws one colour per territory (strong for a player's, pale for a neutral one), water dark blue, a thin dark line on each border between places, a white tile on each door and a black square on each home town, at 10 px per tile.
- `vmap.py`: `VmapRenderer`, which calls `vcmi/export.py`, `vcmi/players.py` and the `.vmap` writer. It takes the `ModContent` the map's objects may come from.

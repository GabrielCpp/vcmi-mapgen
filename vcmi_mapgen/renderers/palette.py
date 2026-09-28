"""Hardcoded rendering-presentation constants for terrain — NOT sourced from VCMI config
(unrelated to vcmi.config's identifier resolution, despite sharing a terrain-code key).

`TERRAIN_RGB` is the terrain palette the schematic renders and the overlays share."""

from vcmi_mapgen.core.model.terrain import Terrain

TERRAIN_RGB: dict[Terrain, tuple[int, int, int]] = {
    Terrain.DIRT: (120, 92, 56),
    Terrain.SAND: (214, 191, 130),
    Terrain.GRASS: (86, 140, 56),
    Terrain.SNOW: (225, 232, 238),
    Terrain.SWAMP: (78, 108, 80),
    Terrain.ROUGH: (150, 124, 70),
    Terrain.SUBTERRANEAN: (92, 78, 104),
    Terrain.LAVA: (70, 60, 58),
    Terrain.WATER: (54, 104, 168),
    Terrain.ROCK: (64, 60, 64),
}

# Pixels per tile used by the schematic (non-sprite) renderers.
TERRAIN_TILE_PX = 9

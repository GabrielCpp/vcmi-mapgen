"""Heroes III terrain as VCMI names it: each core `Terrain` with its map code, its VCMI tile
prefix and its name. The core values coincide with the Heroes III codes, so the table changes
no map.
"""

from dataclasses import dataclass

from vcmi_mapgen.core.model.terrain import Terrain


@dataclass(frozen=True)
class TerrainCodes:
    code: int
    prefix: str
    name: str


TERRAINS: dict[Terrain, TerrainCodes] = {
    Terrain.DIRT: TerrainCodes(0, "dt", "dirt"),
    Terrain.SAND: TerrainCodes(1, "sa", "sand"),
    Terrain.GRASS: TerrainCodes(2, "gr", "grass"),
    Terrain.SNOW: TerrainCodes(3, "sn", "snow"),
    Terrain.SWAMP: TerrainCodes(4, "sw", "swamp"),
    Terrain.ROUGH: TerrainCodes(5, "rg", "rough"),
    Terrain.SUBTERRANEAN: TerrainCodes(6, "sb", "subterr"),
    Terrain.LAVA: TerrainCodes(7, "lv", "lava"),
    Terrain.WATER: TerrainCodes(8, "wt", "water"),
    Terrain.ROCK: TerrainCodes(9, "rc", "rock"),
}
BY_PREFIX: dict[str, Terrain] = {c.prefix: t for t, c in TERRAINS.items()}
LAND_NAMES: tuple[str, ...] = tuple(c.name for t, c in TERRAINS.items() if t.is_land)


def name_of(code: int) -> str:
    """The VCMI name of a terrain code, or "" for a code Heroes III does not have."""
    return TERRAINS[Terrain(code)].name if code in TERRAINS else ""


def prefix_of(code: int) -> str:
    return TERRAINS[Terrain(code)].prefix

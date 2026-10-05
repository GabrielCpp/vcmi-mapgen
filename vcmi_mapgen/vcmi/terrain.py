"""Heroes III terrain as VCMI names it: each core `Terrain` with its map code, its VCMI tile
prefix, its name and the id VCMI's config files give it. The core values coincide with the
Heroes III codes, so the table changes no map.

HotA adds highlands and wasteland. A HotA map keeps their codes and tile prefixes in its
files and its renders, and the core reads each as the base terrain it stands in for.
"""

from dataclasses import dataclass

from vcmi_mapgen.core.model.terrain import Terrain


@dataclass(frozen=True)
class TerrainCodes:
    code: int
    prefix: str
    name: str
    config_id: str


TERRAINS: dict[Terrain, TerrainCodes] = {
    Terrain.DIRT: TerrainCodes(0, "dt", "dirt", "dirt"),
    Terrain.SAND: TerrainCodes(1, "sa", "sand", "sand"),
    Terrain.GRASS: TerrainCodes(2, "gr", "grass", "grass"),
    Terrain.SNOW: TerrainCodes(3, "sn", "snow", "snow"),
    Terrain.SWAMP: TerrainCodes(4, "sw", "swamp", "swamp"),
    Terrain.ROUGH: TerrainCodes(5, "rg", "rough", "rough"),
    Terrain.SUBTERRANEAN: TerrainCodes(6, "sb", "subterr", "subterra"),
    Terrain.LAVA: TerrainCodes(7, "lv", "lava", "lava"),
    Terrain.WATER: TerrainCodes(8, "wt", "water", "water"),
    Terrain.ROCK: TerrainCodes(9, "rc", "rock", "rock"),
}
BY_PREFIX: dict[str, Terrain] = {c.prefix: t for t, c in TERRAINS.items()}
BY_CONFIG_ID: dict[str, str] = {c.config_id: c.name for c in TERRAINS.values()}
LAND_NAMES: tuple[str, ...] = tuple(c.name for t, c in TERRAINS.items() if t.is_land)

HOTA_TERRAINS: dict[int, TerrainCodes] = {
    10: TerrainCodes(10, "hl", "highlands", "highlands"),
    11: TerrainCodes(11, "ws", "wasteland", "wasteland"),
}
STAND_IN: dict[str, Terrain] = {"hl": Terrain.GRASS, "ws": Terrain.ROUGH}


def name_of(code: int) -> str:
    """The VCMI name of a terrain code, or "" for a code Heroes III does not have."""
    return TERRAINS[Terrain(code)].name if code in TERRAINS else ""


def prefix_of(code: int) -> str:
    if code in HOTA_TERRAINS:
        return HOTA_TERRAINS[code].prefix
    return TERRAINS[Terrain(code)].prefix


def terrain_of(prefix: str) -> Terrain:
    """The core terrain of a tile prefix: its own, a HotA terrain's stand-in, else grass."""
    if prefix in BY_PREFIX:
        return BY_PREFIX[prefix]
    return STAND_IN.get(prefix, Terrain.GRASS)

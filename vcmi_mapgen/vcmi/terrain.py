"""Heroes III terrain as VCMI names it: each core `Terrain` with its map code, its VCMI tile
prefix, its name and the id VCMI's config files give it. The core values coincide with the
Heroes III codes, so the table changes no map.
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


def name_of(code: int) -> str:
    """The VCMI name of a terrain code, or "" for a code Heroes III does not have."""
    return TERRAINS[Terrain(code)].name if code in TERRAINS else ""


def prefix_of(code: int) -> str:
    return TERRAINS[Terrain(code)].prefix

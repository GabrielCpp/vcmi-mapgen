"""The terrain vocabulary generation reasons with.

`Terrain` values are the core's own. `vcmi.terrain` maps each one to its Heroes III code, VCMI
tile prefix and name. Water and rock are barriers: no zone forms on them and no land object
stands on them.
"""

from enum import IntEnum


class Terrain(IntEnum):
    DIRT = 0
    SAND = 1
    GRASS = 2
    SNOW = 3
    SWAMP = 4
    ROUGH = 5
    SUBTERRANEAN = 6
    LAVA = 7
    WATER = 8
    ROCK = 9

    @property
    def is_water(self) -> bool:
        return self is Terrain.WATER

    @property
    def is_barrier(self) -> bool:
        return self in (Terrain.WATER, Terrain.ROCK)

    @property
    def is_land(self) -> bool:
        return not self.is_barrier

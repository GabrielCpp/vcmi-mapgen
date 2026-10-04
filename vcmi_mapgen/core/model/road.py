"""The road vocabulary: the three road surfaces a tile can carry, by VCMI road index."""

from enum import IntEnum


class Road(IntEnum):
    DIRT = 1
    GRAVEL = 2
    COBBLESTONE = 3

"""How far a hero walks over the straight line on one level: the median, over pairs of
walkable tiles a band of distances apart, of the 8-connected walk between them over their
Chebyshev distance. An open field reads 1 and a maze of one-tile lanes reads far above it.
The band runs from ``NEAR`` to ``FAR`` of the map side, so it scales with the map."""

import random
import statistics

from vcmi_mapgen.core.grid.reach import STEPS8, distances
from vcmi_mapgen.core.model import MapState, Tile
from vcmi_mapgen.core.model.terrain import Terrain

SOURCES = 30
NEAR = 1 / 7
FAR = 5 / 12


def walkable(map_state: MapState, level: int) -> set[Tile]:
    """The land tiles of ``level`` no object blocks."""
    terrain = map_state.terrain.get(level) or []
    return {
        (x, y)
        for y, row in enumerate(terrain)
        for x, t in enumerate(row)
        if t not in (Terrain.WATER, Terrain.ROCK) and not map_state.at(level, x, y).blocking
    }


def route_winding(walk: set[Tile], side: int) -> float | None:
    """The median walk over Chebyshev distance between ``SOURCES`` walkable tiles, drawn by
    a fixed seed, and every tile they reach between ``NEAR`` and ``FAR`` of ``side`` away.
    None when no pair falls in the band."""
    near, far = max(2, round(NEAR * side)), round(FAR * side)
    tiles = sorted(walk)
    sources = random.Random(0).sample(tiles, min(SOURCES, len(tiles)))
    ratios: list[float] = []
    for sx, sy in sources:
        for (x, y), steps in distances(walk, [(sx, sy)], STEPS8).items():
            cheb = max(abs(x - sx), abs(y - sy))
            if near <= cheb <= far:
                ratios.append(steps / cheb)
    return statistics.median(ratios) if ratios else None


def read_winding(map_state: MapState, level: int) -> float | None:
    """The route winding of ``level``, or None when it has no pair to read."""
    terrain = map_state.terrain.get(level)
    if not terrain or not terrain[0]:
        return None
    return route_winding(walkable(map_state, level), max(len(terrain), len(terrain[0])))

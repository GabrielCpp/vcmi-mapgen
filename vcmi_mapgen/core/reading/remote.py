"""The remote runs of one level: free land farther than a reach from every object worth
the walk, flooded into king-connected runs. A guard, a sign, a seal or a portal makes no
land near it worth going to, so the distance skips them. The corpus and a generated map
read alike."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import cast

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.grid.distance import object_distance
from vcmi_mapgen.core.grid.reach import STEPS8, reach
from vcmi_mapgen.core.model import PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain

SCENERY = frozenset({"", Purpose.DECORATION, Purpose.TERRAIN_MODIFIER})
WORTHLESS = SCENERY | {
    Purpose.GUARD,
    Purpose.INFO,
    Purpose.TRANSPORT,
    Purpose.WATER_TRANSPORT,
    Purpose.MINE_SEAL,
    Purpose.UNKNOWN,
}

type Mask = NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class RemoteRun:
    """One run of remote free land: its tiles, its heart, the tile farthest from every
    object worth the walk, and the heart's distance."""

    tiles: frozenset[Tile]
    heart: Tile
    depth: int


def _cells(objs: Iterable[PlacedObject], size: int) -> Iterable[tuple[PlacedObject, Tile, bool]]:
    for o in objs:
        for (x, y), role in o.footprint.at(o.x, o.y):
            if 0 <= x < size and 0 <= y < size:
                yield o, (x, y), role.blocks


def worth_cells(objs: Iterable[PlacedObject], size: int) -> list[Tile]:
    """Every cell of every object worth the walk, on the map."""
    return sorted({t for o, t, _b in _cells(objs, size) if o.purpose not in WORTHLESS})


def free_land(grid: Sequence[Sequence[int]], objs: Iterable[PlacedObject]) -> Mask:
    """The land tiles no object blocks and no object with a purpose covers."""
    size = len(grid)
    free = np.array([[Terrain(c).is_land for c in row] for row in grid], dtype=np.bool_)
    for o, (x, y), blocking in _cells(objs, size):
        if blocking or o.purpose not in SCENERY:
            free[y, x] = False
    return free


def remote_runs(distance: NDArray[np.int64], free: Mask, far: int) -> list[RemoteRun]:
    """The king-connected runs of free tiles ``far`` or more steps from every object worth
    the walk, the largest run first. A run's heart is its deepest tile, the first in tile
    order on a tie."""
    yx = cast(list[list[int]], np.argwhere(free & (distance >= far)).tolist())
    left = {(x, y) for y, x in yx}
    depth = cast(list[list[int]], distance.tolist())
    runs: list[RemoteRun] = []
    while left:
        tiles = frozenset(reach(left, [min(left)], STEPS8))
        left -= tiles
        heart = min(tiles, key=lambda t: (-depth[t[1]][t[0]], t))
        runs.append(RemoteRun(tiles, heart, depth[heart[1]][heart[0]]))
    return sorted(runs, key=lambda r: (-len(r.tiles), r.heart))


def remote_share(distance: NDArray[np.int64], free: Mask, far: int) -> float:
    """The share of free land ``far`` or more steps from every object worth the walk."""
    total = np.count_nonzero(free)
    return np.count_nonzero(free & (distance >= far)) / total if total else 0.0


def level_distance(objs: Sequence[PlacedObject], size: int) -> NDArray[np.int64]:
    """Per tile, the king steps to the nearest cell of an object worth the walk."""
    return object_distance(size, worth_cells(objs, size))

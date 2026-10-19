"""The rooms of one level: how much of its walkable land is open ground and how much is
lane, and how its walls and rooms clump. A lane tile is a walkable tile outside every
all-walkable 2x2 square. A core tile is inside one, and a room is a 4-connected run of
`ROOM_MIN` or more core tiles."""

import statistics
from dataclasses import dataclass
from typing import cast

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.model.terrain import Terrain

ROOM_MIN = 20

type Mask = NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class RoomReading:
    """The lane and open shares of the walkable tiles, the core rooms' count and median
    size, the largest room's share of the walkable tiles and the largest blocked
    component's share of the blocked land."""

    lane_share: float
    open_share: float
    room_count: int
    room_median: float
    room_largest: float
    blocked_giant: float


def _covered(mask: Mask, k: int) -> Mask:
    """The tiles of `mask` inside some all-true `k` x `k` square of it."""
    h, w = mask.shape
    out = np.zeros_like(mask)
    if h < k or w < k:
        return out
    full = np.ones((h - k + 1, w - k + 1), dtype=np.bool_)
    for dy in range(k):
        for dx in range(k):
            full &= mask[dy : dy + h - k + 1, dx : dx + w - k + 1]
    for dy in range(k):
        for dx in range(k):
            out[dy : dy + h - k + 1, dx : dx + w - k + 1] |= full
    return out & mask


def _count(mask: Mask) -> int:
    return np.count_nonzero(mask)


def component_sizes(mask: Mask) -> list[int]:
    """The sizes of the 4-connected components of `mask`."""
    grid = cast(list[list[bool]], mask.tolist())
    h, w = len(grid), len(grid[0]) if grid else 0
    seen = [[False] * w for _ in range(h)]
    sizes: list[int] = []
    for sy in range(h):
        for sx in range(w):
            if not grid[sy][sx] or seen[sy][sx]:
                continue
            seen[sy][sx] = True
            stack = [(sy, sx)]
            n = 0
            while stack:
                y, x = stack.pop()
                n += 1
                for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                    if 0 <= ny < h and 0 <= nx < w and grid[ny][nx] and not seen[ny][nx]:
                        seen[ny][nx] = True
                        stack.append((ny, nx))
            sizes.append(n)
    return sizes


def read_rooms(map_state: MapState, level: int) -> RoomReading | None:
    """The rooms reading of `level`, or None when the level has no walkable land."""
    terrain = map_state.terrain.get(level)
    if not terrain or not terrain[0]:
        return None
    land = np.array(
        [[t not in (Terrain.WATER, Terrain.ROCK) for t in row] for row in terrain], dtype=np.bool_
    )
    blocking = np.array(
        [
            [map_state.at(level, x, y).blocking for x in range(len(row))]
            for y, row in enumerate(terrain)
        ],
        dtype=np.bool_,
    )
    walk = land & ~blocking
    count = _count(walk)
    if not count:
        return None
    core = _covered(walk, 2)
    rooms = [n for n in component_sizes(core) if n >= ROOM_MIN]
    blocked = land & blocking
    giants = component_sizes(blocked)
    return RoomReading(
        lane_share=_count(walk & ~core) / count,
        open_share=_count(_covered(walk, 3)) / count,
        room_count=len(rooms),
        room_median=float(statistics.median(rooms)) if rooms else 0.0,
        room_largest=max(rooms, default=0) / count,
        blocked_giant=max(giants, default=0) / _count(blocked) if giants else 0.0,
    )

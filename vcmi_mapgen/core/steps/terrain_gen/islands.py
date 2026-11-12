"""Islands raised out of the flooded sea, each a new place at a corpus island's share of
the map. An island stands ``STRAIT`` water tiles or more from every other land and from
the map edge, so a boat sails around it and the sea stays one."""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from typing import cast

import numpy as np
from numpy.typing import NDArray

type Mask = NDArray[np.bool_]
type Labels = NDArray[np.int64]
type Field = NDArray[np.float64]

STRAIT = 3
MIN_TILES = 4
STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def _reach(land: Mask) -> Field:
    """Each tile's 4-step distance to the nearest land tile or the off-map ring."""
    h, w = land.shape
    out: Field = np.full((h, w), np.inf)
    frontier = [(x, y) for y in range(h) for x in range(w) if land[y, x]]
    for x, y in frontier:
        out[y, x] = 0.0
    ring = np.ones((h, w), dtype=np.bool_)
    ring[1:-1, 1:-1] = False
    out[ring & ~land] = 1.0
    frontier += [(x, y) for y in range(h) for x in range(w) if out[y, x] == 1.0]
    d = 0.0
    while frontier:
        d += 1.0
        nxt: list[tuple[int, int]] = []
        for x, y in frontier:
            for dx, dy in STEPS:
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and out[ny, nx] > out[y, x] + 1.0:
                    out[ny, nx] = out[y, x] + 1.0
                    nxt.append((nx, ny))
        frontier = nxt
    return out


def _disk(side: int, centre: tuple[int, int], radius: float) -> Mask:
    """The tiles of a ``side`` square within ``radius`` of ``centre``."""
    axis = np.arange(side, dtype=np.float64)
    dx = (axis - centre[0]) ** 2
    dy = (axis - centre[1]) ** 2
    return dy[:, None] + dx[None, :] <= radius * radius


def _blob(
    room: Mask, seed: tuple[int, int], size: int, rng: random.Random
) -> list[tuple[int, int]]:
    """A round 4-connected blob of up to ``size`` tiles of ``room`` grown from ``seed``,
    each next tile drawn by how many blob tiles it touches."""
    h, w = room.shape
    blob = {seed}
    rim: dict[tuple[int, int], int] = {}
    tiles = [seed]

    def touch(x: int, y: int) -> None:
        for dx, dy in STEPS:
            t = (x + dx, y + dy)
            if 0 <= t[0] < w and 0 <= t[1] < h and room[t[1], t[0]] and t not in blob:
                rim[t] = rim.get(t, 0) + 1

    touch(*seed)
    while len(tiles) < size and rim:
        keys = sorted(rim)
        t = rng.choices(keys, [rim[k] ** 3 for k in keys])[0]
        del rim[t]
        blob.add(t)
        tiles.append(t)
        touch(*t)
    return tiles


def raise_islands(
    label: Labels, shares: Sequence[float], places: int, rng: random.Random
) -> tuple[Labels, int]:
    """``label`` with an island raised on the water for each share in ``shares``, largest
    first, each numbered as the next place after ``places``, and the places it holds after.
    An island stays inside the disk its seed's open water holds, so a narrow sea gets
    a small round island and never a strip, and one under ``MIN_TILES`` is dropped."""
    out = label.copy()
    side = out.shape[0]
    count = places
    for share in sorted(shares, reverse=True):
        size = round(share * side * side)
        if size < MIN_TILES:
            continue
        reach = _reach(out >= 0)
        room: Mask = reach > STRAIT
        if not room.any():
            break
        radius = math.sqrt(size / math.pi)
        best = max(cast("list[float]", reach[room].tolist()))
        deep = room & (reach >= min(best, STRAIT + radius))
        ys, xs = (cast("list[int]", a.tolist()) for a in np.nonzero(deep))
        pick = rng.randrange(len(xs))
        sx, sy = xs[pick], ys[pick]
        disk = _disk(side, (sx, sy), reach.item(sy, sx) - STRAIT)
        tiles = _blob(room & disk, (sx, sy), size, rng)
        if len(tiles) < MIN_TILES:
            continue
        for x, y in tiles:
            out[y, x] = count
        count += 1
    return out, count

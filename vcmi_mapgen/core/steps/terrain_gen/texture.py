"""Boundary texturing: Gibbs sweeps of the corpus terrain Markov tables, clamped to a band
around each terrain change."""

import collections
import random
from collections.abc import Collection

from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.priors.markov import MarkovTables

BAND = 2  # boundary-texturing band half-width (tiles)


def sample(counter: collections.Counter[int], rnd: random.Random) -> int:
    tot = sum(counter.values())
    r = rnd.random() * tot
    acc = 0
    for k, v in counter.items():
        acc += v
        if r <= acc:
            return k
    return next(iter(counter))


def border_band(grid: list[list[int]]) -> list[list[bool]]:
    H = len(grid)
    W = len(grid[0])
    band = [[False] * W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            t = grid[y][x]
            if any(
                0 <= x + dx < W and 0 <= y + dy < H and grid[y + dy][x + dx] != t
                for dx in (-1, 0, 1)
                for dy in (-1, 0, 1)
            ):
                for dy in range(-BAND, BAND + 1):
                    for dx in range(-BAND, BAND + 1):
                        if 0 <= x + dx < W and 0 <= y + dy < H:
                            band[y + dy][x + dx] = True
    return band


def texture_boundaries(
    grid: list[list[int]],
    rng: random.Random,
    tables: MarkovTables,
    sweeps: int = 3,
    protect: Collection[Tile] = (),
) -> list[list[int]]:
    """Isotropic Gibbs sweeps of the learned 4-neighbour terrain conditional, RESTRICTED to
    tiles within BAND (Chebyshev) of a terrain change; everything else is clamped, so the
    interiors keep their planned terrain and only the borders gain corpus transition texture.
    `tables` are the corpus transitions of the grid's terrain level. `protect`
    cells (e.g. underground tunnel corridors, which are thin enough to sit entirely inside
    the band on both sides) are excluded from resampling so a rock-heavy corpus conditional
    can't erode a load-bearing connection back into barrier."""
    H = len(grid)
    W = len(grid[0])
    M4 = tables.chain4
    M = tables.chain
    band = border_band(grid)
    tiles = [
        (x, y)
        for y in range(1, H - 1)
        for x in range(1, W - 1)
        if band[y][x] and (x, y) not in protect
    ]
    for _ in range(sweeps):
        rng.shuffle(tiles)
        for x, y in tiles:
            lf, u = grid[y][x - 1], grid[y - 1][x]
            r, d = grid[y][x + 1], grid[y + 1][x]
            if sum(M4.full[(lf, u, r, d)].values()) >= 10:
                dist = M4.full[(lf, u, r, d)]
            else:
                dist = collections.Counter[int]()
                dist.update(M4.horiz[(lf, r)])
                dist.update(M4.vert[(u, d)])
                if not dist:
                    dist = M.marg
            grid[y][x] = sample(dist, rng)
    return grid

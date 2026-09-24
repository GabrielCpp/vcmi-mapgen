"""Terrain Markov chain LEARNED from the 159 real maps (the user's idea #1).

P(terrain[x,y] | left, up, up-left), estimated from real surface terrain, sampled
in raster order with back-off. This reproduces the real LOCAL texture (patch sizes,
coastlines, how terrains border each other) instead of arbitrary noise blobs.
"""

import collections
import random
from dataclasses import dataclass

from vcmi_mapgen.kit import objects as OR


@dataclass(slots=True)
class MarkovModel:
    full: collections.defaultdict[tuple[int, int, int], collections.Counter[int]]
    pair: collections.defaultdict[tuple[int, int], collections.Counter[int]]
    one: collections.defaultdict[tuple[int], collections.Counter[int]]
    marg: collections.Counter[int]


@dataclass(slots=True)
class MarkovModel4:
    full: collections.defaultdict[tuple[int, int, int, int], collections.Counter[int]]
    horiz: collections.defaultdict[tuple[int, int], collections.Counter[int]]
    vert: collections.defaultdict[tuple[int, int], collections.Counter[int]]


def learn(level_index: int) -> MarkovModel:
    """counts for P(center | left, up, upleft) over real maps at the given level."""
    full: collections.defaultdict[tuple[int, int, int], collections.Counter[int]] = (
        collections.defaultdict(collections.Counter)
    )  # (l,u,ul)->center
    pair: collections.defaultdict[tuple[int, int], collections.Counter[int]] = (
        collections.defaultdict(collections.Counter)
    )  # (l,u)->center
    one: collections.defaultdict[tuple[int], collections.Counter[int]] = collections.defaultdict(
        collections.Counter
    )  # (l,)->center
    marg: collections.Counter[int] = collections.Counter()
    for name in OR.all_map_names():
        m = OR.load_faithful(name)
        if level_index >= len(m.terrain):
            continue
        g = m.terrain[level_index]
        H = len(g)
        W = len(g[0])
        T = [[c.t for c in row] for row in g]
        for y in range(H):
            for x in range(W):
                c = T[y][x]
                marg[c] += 1
                lf = T[y][x - 1] if x > 0 else None
                u = T[y - 1][x] if y > 0 else None
                ul = T[y - 1][x - 1] if (x > 0 and y > 0) else None
                if lf is not None and u is not None and ul is not None:
                    full[(lf, u, ul)][c] += 1
                if lf is not None and u is not None:
                    pair[(lf, u)][c] += 1
                if lf is not None:
                    one[(lf,)][c] += 1
    return MarkovModel(full=full, pair=pair, one=one, marg=marg)


def sample(counter: collections.Counter[int], rnd: random.Random) -> int:
    tot = sum(counter.values())
    r = rnd.random() * tot
    acc = 0
    for k, v in counter.items():
        acc += v
        if r <= acc:
            return k
    return next(iter(counter))


def generate(
    model: MarkovModel, W: int, H: int, rnd: random.Random, thresh: int = 12
) -> list[list[int]]:
    g = [[0] * W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            lf = g[y][x - 1] if x > 0 else None
            u = g[y - 1][x] if y > 0 else None
            ul = g[y - 1][x - 1] if (x > 0 and y > 0) else None
            dist: collections.Counter[int]
            if (
                lf is not None
                and u is not None
                and ul is not None
                and sum(model.full[(lf, u, ul)].values()) >= thresh
            ):
                dist = model.full[(lf, u, ul)]
            elif lf is not None and u is not None and sum(model.pair[(lf, u)].values()) >= thresh:
                dist = model.pair[(lf, u)]
            elif lf is not None and sum(model.one[(lf,)].values()) >= 1:
                dist = model.one[(lf,)]
            else:
                dist = model.marg
            g[y][x] = sample(dist, rnd)
    return g


def learn4(level_index: int) -> MarkovModel4:
    """P(center | left,up,right,down) for isotropic Gibbs, with back-off tables."""
    full: collections.defaultdict[tuple[int, int, int, int], collections.Counter[int]] = (
        collections.defaultdict(collections.Counter)
    )  # (l,u,r,d)->c
    horiz: collections.defaultdict[tuple[int, int], collections.Counter[int]] = (
        collections.defaultdict(collections.Counter)
    )  # (l,r)->c
    vert: collections.defaultdict[tuple[int, int], collections.Counter[int]] = (
        collections.defaultdict(collections.Counter)
    )  # (u,d)->c
    for name in OR.all_map_names():
        m = OR.load_faithful(name)
        if level_index >= len(m.terrain):
            continue
        g = m.terrain[level_index]
        H = len(g)
        W = len(g[0])
        T = [[c.t for c in row] for row in g]
        for y in range(1, H - 1):
            for x in range(1, W - 1):
                c = T[y][x]
                lf = T[y][x - 1]
                u = T[y - 1][x]
                r = T[y][x + 1]
                d = T[y + 1][x]
                full[(lf, u, r, d)][c] += 1
                horiz[(lf, r)][c] += 1
                vert[(u, d)][c] += 1
    return MarkovModel4(full=full, horiz=horiz, vert=vert)


def gibbs(
    grid: list[list[int]],
    M4: MarkovModel4,
    marg: collections.Counter[int],
    rnd: random.Random,
    sweeps: int = 5,
    thresh: int = 10,
) -> list[list[int]]:
    H = len(grid)
    W = len(grid[0])
    for _ in range(sweeps):
        for y in range(1, H - 1):
            for x in range(1, W - 1):
                lf = grid[y][x - 1]
                u = grid[y - 1][x]
                r = grid[y][x + 1]
                d = grid[y + 1][x]
                if sum(M4.full[(lf, u, r, d)].values()) >= thresh:
                    dist = M4.full[(lf, u, r, d)]
                else:
                    dist = collections.Counter[int]()
                    dist.update(M4.horiz[(lf, r)])
                    dist.update(M4.vert[(u, d)])
                    if not dist:
                        dist = marg
                grid[y][x] = sample(dist, rnd)
    return grid


if __name__ == "__main__":
    rnd = random.Random(3)
    print("learning surface terrain Markov from 159 maps...")
    M = learn(0)
    M4 = learn4(0)
    marginal = dict(M.marg.most_common())
    print(f"  contexts: full={len(M.full)} pair={len(M.pair)}  marginal terrains={marginal}")
    W = H = 72
    gen = generate(M, W, H, rnd)  # raster init
    geng = [row[:] for row in gen]
    _ = gibbs(geng, M4, M.marg, rnd, sweeps=6)  # isotropic smoothing
    hist = collections.Counter(t for row in geng for t in row)
    print("  post-Gibbs terrain histogram:", dict(hist.most_common()))

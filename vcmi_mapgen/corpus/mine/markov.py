"""Terrain Markov chain LEARNED from the 159 real maps (the user's idea #1).

P(terrain[x,y] | left, up, up-left), estimated from real surface terrain, sampled
in raster order with back-off. This reproduces the real LOCAL texture (patch sizes,
coastlines, how terrains border each other) instead of arbitrary noise blobs.
"""

import collections
from collections.abc import Iterable

from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.priors.markov import MarkovModel, MarkovModel4


def learn(level_index: int, maps: Iterable[MapState]) -> MarkovModel:
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
    for m in maps:
        if level_index >= len(m.terrain):
            continue
        g = m.terrain[level_index]
        H = len(g)
        W = len(g[0])
        T = [[int(t) for t in row] for row in g]
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


def learn4(level_index: int, maps: Iterable[MapState]) -> MarkovModel4:
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
    for m in maps:
        if level_index >= len(m.terrain):
            continue
        g = m.terrain[level_index]
        H = len(g)
        W = len(g[0])
        T = [[int(t) for t in row] for row in g]
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

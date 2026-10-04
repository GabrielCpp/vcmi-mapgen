"""The palette partition π (map-math 1.4): the places grouped into palette regions, each a
union of whole places connected on the realised place adjacency. Identity draws one
dominant terrain per region."""

import math
import random
from collections import deque
from collections.abc import Collection, Sequence

from vcmi_mapgen.core.priors.places import PaletteCount
from vcmi_mapgen.core.steps.terrain_gen.place_graph import NEAREST_RECORDS, Edge


def neighbours(n: int, adjacency: Collection[Edge]) -> list[list[int]]:
    """Each place's adjacent places, in increasing order."""
    nbr: list[list[int]] = [[] for _ in range(n)]
    for a, b in sorted(adjacency):
        nbr[a].append(b)
        nbr[b].append(a)
    return nbr


def components(nbr: Sequence[Sequence[int]]) -> list[list[int]]:
    """The connected components of the place adjacency, each in increasing order."""
    seen = [False] * len(nbr)
    out: list[list[int]] = []
    for start in range(len(nbr)):
        if seen[start]:
            continue
        seen[start] = True
        comp, queue = [start], deque([start])
        while queue:
            for q in nbr[queue.popleft()]:
                if not seen[q]:
                    seen[q] = True
                    comp.append(q)
                    queue.append(q)
        out.append(sorted(comp))
    return out


def palette_count(
    counts: Sequence[PaletteCount], n: int, land: int, floor: int, rng: random.Random
) -> int:
    """A corpus palette region count for ``n`` places on ``land`` tiles. The record is drawn
    among the ones whose place count is nearest ``n``, closest in land first, and its region
    count is scaled by ``n`` over its place count. The count lies between ``floor`` and
    ``n``."""
    if not counts:
        return max(floor, min(n, 1))
    group = sorted(
        counts,
        key=lambda c: (abs(math.log(c.places / n)), abs(math.log(c.land / land)), c.regions),
    )
    rec = rng.choice(group[:NEAREST_RECORDS])
    return max(floor, min(n, round(rec.regions * n / rec.places)))


def draw_palette(
    counts: Sequence[PaletteCount],
    areas: Sequence[int],
    label: Sequence[Sequence[int]],
    adjacency: Collection[Edge],
    rng: random.Random,
) -> tuple[int, list[int]]:
    """The drawn palette region count and each place's region for the place map ``label``
    with its realised ``adjacency``. The count is never below the number of connected
    components of ``adjacency``."""
    n = max((z for row in label for z in row), default=-1) + 1
    sizes = [0] * n
    for row in label:
        for z in row:
            if z >= 0:
                sizes[z] += 1
    floor = len(components(neighbours(n, adjacency)))
    k = palette_count(counts, n, sum(sizes), floor, rng)
    return k, group_places(sizes, adjacency, k, areas, rng)


def _hops(nbr: Sequence[Sequence[int]], seeds: Collection[int]) -> list[float]:
    dist = [math.inf] * len(nbr)
    queue = deque(seeds)
    for s in seeds:
        dist[s] = 0
    while queue:
        p = queue.popleft()
        for q in nbr[p]:
            if dist[q] == math.inf:
                dist[q] = dist[p] + 1
                queue.append(q)
    return dist


def _seeds(nbr: Sequence[Sequence[int]], k: int, rng: random.Random) -> list[int]:
    seeds = [rng.choice(comp) for comp in components(nbr)]
    while len(seeds) < k:
        dist = _hops(nbr, seeds)
        far = max(dist)
        seeds.append(rng.choice([p for p, d in enumerate(dist) if d == far]))
    return seeds


def group_places(
    sizes: Sequence[int],
    adjacency: Collection[Edge],
    k: int,
    areas: Sequence[int],
    rng: random.Random,
) -> list[int]:
    """Each place's palette region. One seed per connected component of ``adjacency``, the
    rest farthest-first by hop distance, so there are ``k`` regions or one per component
    when there are more components. Each region's capacity is a corpus terrain-blob area
    from ``areas``, renormalised to the sum of ``sizes``. The least filled region under its
    capacity takes the frontier place it touches most, until none can grow, then the least
    filled region with a frontier takes the rest. Every region is a union of whole places
    connected on ``adjacency``."""
    nbr = neighbours(len(sizes), adjacency)
    seeds = _seeds(nbr, min(k, len(sizes)), rng)
    drawn = [rng.choice(areas) if areas else 1 for _ in seeds]
    caps = [d * sum(sizes) / sum(drawn) for d in drawn]
    group = [-1] * len(sizes)
    fill = [0.0] * len(seeds)
    for r, s in enumerate(seeds):
        group[s] = r
        fill[r] = sizes[s]
    capped = True
    while -1 in group:
        frontier = [
            sorted({q for p, g in enumerate(group) if g == r for q in nbr[p] if group[q] < 0})
            for r in range(len(seeds))
        ]
        open_ = [r for r, f in enumerate(frontier) if f and (fill[r] < caps[r] or not capped)]
        if not open_:
            capped = False
            continue
        r = min(open_, key=lambda r: (fill[r] / caps[r], r))
        touch = [sum(group[o] == r for o in nbr[q]) for q in frontier[r]]
        best = max(touch)
        q = rng.choice([q for q, t in zip(frontier[r], touch, strict=True) if t == best])
        group[q] = r
        fill[r] += sizes[q]
    return group

"""The first labelling of place inference: seeds, the geodesic Voronoi growth under the
soft-barrier metric, and the completion that makes the label total on land."""

import collections
import heapq
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass

from vcmi_mapgen.core.grid.components import components
from vcmi_mapgen.core.grid.reach import STEPS4, distances
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.reading.ground import Ground, TownKey

LAMBDA = 2.0
WINDOW = 2
MIN_SEED_AREA = 40
POCKET_MIN_AREA = 10
ANCHOR_REACH = 8


@dataclass(frozen=True, slots=True)
class Growth:
    """Each land tile's first label, and the towns each label holds."""

    labels: Mapping[Tile, int]
    towns: Mapping[int, tuple[TownKey, ...]]
    anchors: Mapping[int, Tile]


def soft_barrier(ground: Ground) -> dict[Tile, float]:
    """For every walkable tile, the fraction of non-walkable tiles in the 5x5 window about
    it, counting only the window's tiles that lie on the map."""
    w, h = ground.width, ground.height
    acc = [[0] * (w + 1) for _ in range(h + 1)]
    for y in range(h):
        for x in range(w):
            hit = 0 if (x, y) in ground.walk else 1
            acc[y + 1][x + 1] = hit + acc[y][x + 1] + acc[y + 1][x] - acc[y][x]
    out: dict[Tile, float] = {}
    for x, y in ground.walk:
        x0, x1 = max(0, x - WINDOW), min(w, x + WINDOW + 1)
        y0, y1 = max(0, y - WINDOW), min(h, y + WINDOW + 1)
        n = acc[y1][x1] - acc[y0][x1] - acc[y1][x0] + acc[y0][x0]
        out[(x, y)] = n / ((x1 - x0) * (y1 - y0))
    return out


def town_anchor(ground: Ground, grow: Collection[Tile], cells: Iterable[Tile]) -> Tile | None:
    """The grow tile nearest a town's cells, within ``ANCHOR_REACH`` steps."""
    d = dict.fromkeys(sorted(cells), 0)
    q = collections.deque(d)
    while q:
        cur = q.popleft()
        if cur in grow:
            return cur
        if d[cur] >= ANCHOR_REACH:
            continue
        for dx, dy in STEPS4:
            n = (cur[0] + dx, cur[1] + dy)
            if ground.inside(n) and n not in d:
                d[n] = d[cur] + 1
                q.append(n)
    return None


def _farthest(d: Mapping[Tile, int]) -> Tile:
    return min(d, key=lambda t: (-d[t], t))


def geodesic_centre(tiles: Collection[Tile]) -> Tile:
    """The tile of a connected set that best balances its two farthest-apart ends."""
    a = _farthest(distances(tiles, [min(tiles)]))
    da = distances(tiles, [a])
    db = distances(tiles, [_farthest(da)])
    return min(tiles, key=lambda t: (max(da[t], db[t]), abs(da[t] - db[t]), t))


def _seeds(ground: Ground, grow: frozenset[Tile]) -> tuple[list[Tile], dict[int, list[TownKey]]]:
    seeds: list[Tile] = []
    towns: dict[int, list[TownKey]] = {}
    for site in ground.towns:
        anchor = town_anchor(ground, grow, site.cells)
        if anchor is None:
            continue
        if anchor not in seeds:
            seeds.append(anchor)
        towns.setdefault(seeds.index(anchor), []).append(site.key)
    return seeds, towns


def _grow(grow: frozenset[Tile], seeds: list[Tile], cost: Mapping[Tile, float]) -> dict[Tile, int]:
    label: dict[Tile, int] = {}
    heap = [(0.0, i, s) for i, s in enumerate(seeds)]
    heapq.heapify(heap)
    while heap:
        d, i, cur = heapq.heappop(heap)
        if cur in label:
            continue
        label[cur] = i
        for dx, dy in STEPS4:
            n = (cur[0] + dx, cur[1] + dy)
            if n in grow and n not in label:
                heapq.heappush(heap, (d + 1.0 + LAMBDA * cost[n], i, n))
    return label


def spread(labels: dict[Tile, int], region: Collection[Tile]) -> None:
    """Give every unlabelled tile of ``region`` the label of the labelled tile it is
    nearest to through ``region``, breaking ties by sorted source order."""
    q = collections.deque(sorted(labels))
    while q:
        cur = q.popleft()
        for dx, dy in STEPS4:
            n = (cur[0] + dx, cur[1] + dy)
            if n in region and n not in labels:
                labels[n] = labels[cur]
                q.append(n)


def _complete(ground: Ground, labels: dict[Tile, int]) -> dict[Tile, int]:
    if not labels and ground.land:
        labels[min(ground.land)] = 0
    spread(labels, ground.walk)
    spread(labels, ground.land)
    every = {(x, y) for x in range(ground.width) for y in range(ground.height)}
    spread(labels, every)
    return {t: lab for t, lab in labels.items() if t in ground.land}


def grow_places(ground: Ground) -> Growth:
    """Seed every town and every town-less guard-free component of at least
    ``MIN_SEED_AREA`` tiles, grow the seeds over the walkable tiles outside the zones of
    control, keep each smaller component of at least ``POCKET_MIN_AREA`` tiles as its own
    label, and spread the labels over the rest of the land."""
    grow = ground.walk - ground.zoc
    seeds, towns = _seeds(ground, grow)
    comp = components(grow)
    members: dict[int, list[Tile]] = collections.defaultdict(list)
    for t in sorted(comp):
        members[comp[t]].append(t)
    seeded = {comp[s] for s in seeds}
    pockets: list[list[Tile]] = []
    for c, tiles in sorted(members.items()):
        if c in seeded or len(tiles) < POCKET_MIN_AREA:
            continue
        if len(tiles) >= MIN_SEED_AREA:
            seeds.append(geodesic_centre(tiles))
        else:
            pockets.append(tiles)
    labels = _grow(grow, seeds, soft_barrier(ground))
    for tiles in pockets:
        labels.update(dict.fromkeys(tiles, len(seeds)))
        seeds.append(tiles[0])
    return Growth(
        labels=_complete(ground, labels),
        towns={i: tuple(keys) for i, keys in towns.items()},
        anchors=dict(enumerate(seeds)),
    )

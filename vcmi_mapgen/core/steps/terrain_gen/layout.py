"""The layout of a place graph on land (map-math 4.2): anchors from classical scaling of the
graph distances, regions grown from them to their target sizes, and a few nudged regrowths
until the regions border the way the graph says."""

import collections
import math
import random
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import cast

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.grid.components import components
from vcmi_mapgen.core.grid.reach import STEPS4, distances
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.reading.places import PlaceRole
from vcmi_mapgen.core.steps.terrain_gen.macro import grow_regions
from vcmi_mapgen.core.steps.terrain_gen.place_graph import HOME_FLOOR, Edge, PlaceGraph
from vcmi_mapgen.core.steps.terrain_gen.place_map import label_adjacency

TRIES = 5
NUDGE = 0.3
MARGIN = 0.08
SPREAD = 0.6
SPREAD_ROUNDS = 12
SNAP_GAP = 0.75
ROOM_FILL = 0.9

type Land = Sequence[Sequence[bool]]
type Point = tuple[float, float]
type Mask = NDArray[np.bool_]
type Labels = NDArray[np.int64]


@dataclass(frozen=True, slots=True)
class Layout:
    """``label[y][x]`` is the place of a land tile and -1 off land. Places past the graph's
    are pockets grown on land no anchor reached. ``missing`` holds the planned edges the
    regions do not realise, ``home_contacts`` the realised edges between two homes, and
    ``home_gap`` the least walkable distance between two home anchors over the side.
    ``starved`` counts the homes that grew smaller than their floor."""

    label: list[list[int]]
    anchors: tuple[Tile, ...]
    places: int
    missing: frozenset[Edge]
    home_contacts: int
    home_gap: float
    starved: int


def graph_distances(graph: PlaceGraph) -> NDArray[np.float64]:
    """Shortest path lengths over the graph, an edge as long as the two places' radii, with
    every two homes put as far apart as the farthest pair."""
    n = len(graph.roles)
    radius = [math.sqrt(s / math.pi) for s in graph.sizes]
    d: NDArray[np.float64] = np.full((n, n), np.inf, dtype=np.float64)
    np.fill_diagonal(d, 0.0)
    for a, b in graph.edges:
        d[a, b] = d[b, a] = radius[a] + radius[b]
    for k in range(n):
        d = np.minimum(d, d[:, k : k + 1] + d[k : k + 1, :])
    finite: NDArray[np.bool_] = np.isfinite(d)
    far = float(np.max(d, where=finite, initial=1.0))
    d[~finite] = far
    homes = [i for i, r in enumerate(graph.roles) if r == PlaceRole.HOME]
    apart: NDArray[np.bool_] = np.zeros((n, n), dtype=np.bool_)
    for a in homes:
        for b in homes:
            apart[a, b] = a != b
    return np.where(apart, np.maximum(d, far), d)


def classical_scaling(d: NDArray[np.float64]) -> list[Point]:
    """The two-dimensional points whose distances best match ``d``, by classical MDS."""
    n = d.shape[0]
    j: NDArray[np.float64] = np.eye(n) - np.ones((n, n)) / n
    b: NDArray[np.float64] = -0.5 * (j @ (d**2) @ j)
    vals, vecs = np.linalg.eigh(b)
    eig = cast(list[float], vals.tolist())
    rows = cast(list[list[float]], vecs.tolist())
    top = sorted(range(n), key=lambda k: -eig[k])[:2]
    scale = [math.sqrt(max(eig[k], 0.0)) for k in top]
    cols = [[rows[i][k] * sc for i in range(n)] for k, sc in zip(top, scale, strict=True)]
    while len(cols) < 2:
        cols.append([0.0] * n)
    return list(zip(cols[0], cols[1], strict=True))


def _land_tiles(land: Land) -> list[Tile]:
    return [(x, y) for y, row in enumerate(land) for x, v in enumerate(row) if v]


def main_land(land: Land) -> list[list[bool]]:
    """The largest four-connected land mass of ``land``, the lowest-numbered on a tie."""
    comp = components(frozenset(_land_tiles(land)))
    sizes = collections.Counter(comp.values())
    keep = min(sizes, key=lambda c: (-sizes[c], c), default=-1)
    return [[comp.get((x, y)) == keep for x in range(len(row))] for y, row in enumerate(land)]


def _stretch(values: Sequence[float], lo: float, hi: float) -> list[float]:
    vmin, vmax = min(values), max(values)
    span = vmax - vmin if vmax - vmin > 1e-9 else 1.0
    return [lo + (v - vmin) / span * (hi - lo) for v in values]


def fit_to_land(points: Sequence[Point], land: Land, rng: random.Random) -> list[Point]:
    """``points`` turned by a random angle, maybe mirrored, and stretched over the land's
    bounding box inside a margin."""
    theta = rng.uniform(0.0, 2.0 * math.pi)
    c, s = math.cos(theta), math.sin(theta)
    mirror = -1.0 if rng.random() < 0.5 else 1.0
    turned = [(mirror * (x * c - y * s), x * s + y * c) for x, y in points]
    tiles = _land_tiles(land)
    xs = [x for x, _ in tiles]
    ys = [y for _, y in tiles]
    m = MARGIN * len(land)
    px = _stretch([x for x, _ in turned], min(xs) + m, max(xs) - m)
    py = _stretch([y for _, y in turned], min(ys) + m, max(ys) - m)
    return list(zip(px, py, strict=True))


def spread(points: Sequence[Point], gap: float) -> list[Point]:
    """``points`` pushed apart until no two sit closer than ``gap``, or the rounds run out."""
    pts = [list(p) for p in points]
    for _ in range(SPREAD_ROUNDS):
        moved = False
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                dx, dy = pts[j][0] - pts[i][0], pts[j][1] - pts[i][1]
                dist = math.hypot(dx, dy)
                if dist >= gap:
                    continue
                ux, uy = (dx / dist, dy / dist) if dist > 1e-9 else (1.0, 0.0)
                push = (gap - dist) / 2
                pts[i][0] -= ux * push
                pts[i][1] -= uy * push
                pts[j][0] += ux * push
                pts[j][1] += uy * push
                moved = True
        if not moved:
            break
    return [(p[0], p[1]) for p in pts]


def separate(points: Sequence[Point], movers: Sequence[int], gap: float, land: Land) -> list[Point]:
    """``points`` with every two of ``movers`` pushed apart until they sit ``gap`` apart, or
    the rounds run out, each kept inside the land's bounding box."""
    tiles = _land_tiles(land)
    lo_x, hi_x = min(x for x, _ in tiles), max(x for x, _ in tiles)
    lo_y, hi_y = min(y for _, y in tiles), max(y for _, y in tiles)
    pts = [list(p) for p in points]
    for _ in range(SPREAD_ROUNDS):
        moved = False
        for k, i in enumerate(movers):
            for j in movers[k + 1 :]:
                dx, dy = pts[j][0] - pts[i][0], pts[j][1] - pts[i][1]
                dist = math.hypot(dx, dy)
                if dist >= gap:
                    continue
                ux, uy = (dx / dist, dy / dist) if dist > 1e-9 else (1.0, 0.0)
                push = (gap - dist) / 2
                pts[i] = [
                    min(hi_x, max(lo_x, pts[i][0] - ux * push)),
                    min(hi_y, max(lo_y, pts[i][1] - uy * push)),
                ]
                pts[j] = [
                    min(hi_x, max(lo_x, pts[j][0] + ux * push)),
                    min(hi_y, max(lo_y, pts[j][1] + uy * push)),
                ]
                moved = True
        if not moved:
            break
    return [(p[0], p[1]) for p in pts]


def roomy(land: Land, side: int) -> frozenset[Tile]:
    """The land tiles whose centred square of ``side`` tiles lies on the map and is at least
    ``ROOM_FILL`` land."""
    H, W = len(land), len(land[0])
    acc = [[0] * (W + 1) for _ in range(H + 1)]
    for y in range(H):
        for x in range(W):
            acc[y + 1][x + 1] = acc[y][x + 1] + acc[y + 1][x] - acc[y][x] + int(land[y][x])
    h = side // 2
    need = ROOM_FILL * side * side
    return frozenset(
        (x, y)
        for x, y in _land_tiles(land)
        if h <= x < W - h
        and h <= y < H - h
        and acc[y + h + 1][x + h + 1]
        - acc[y - h][x + h + 1]
        - acc[y + h + 1][x - h]
        + acc[y - h][x - h]
        >= need
    )


def snap(
    points: Sequence[Point],
    land: Land,
    order: Sequence[int],
    gap: float,
    room: Mapping[int, AbstractSet[Tile]],
) -> list[Tile]:
    """Each point's nearest land tile, taken in ``order``. The tile lies in the point's
    ``room`` while one is free there, and at least ``gap`` from every tile an earlier point
    took while such a tile is left."""
    free: Mask = np.array(land, dtype=np.bool_)
    h, w = free.shape
    xs, ys = _coords(h, w)
    rooms = {i: _mask(tiles, h, w) for i, tiles in room.items()}
    near: Mask = np.zeros((h, w), dtype=np.bool_)
    out: dict[int, Tile] = {}
    for i in order:
        own = free & rooms[i] if i in rooms else free
        own = own if own.any() else free
        pool = own & ~near
        pool = pool if pool.any() else own
        if not pool.any():
            raise ValueError("snap needs a free land tile for every point")
        px, py = points[i]
        d2 = np.where(pool, (xs - px) ** 2 + (ys - py) ** 2, np.inf)
        y, x = divmod(int(np.argmin(d2)), w)
        free[y, x] = False
        near |= (xs - x) ** 2 + (ys - y) ** 2 < gap * gap
        out[i] = (x, y)
    return [out[i] for i in range(len(points))]


def _coords(h: int, w: int) -> tuple[Labels, Labels]:
    xs = np.tile(np.arange(w, dtype=np.int64), h).reshape(h, w)
    ys = np.repeat(np.arange(h, dtype=np.int64), w).reshape(h, w)
    return xs, ys


def _mask(tiles: AbstractSet[Tile], h: int, w: int) -> Mask:
    mask: Mask = np.zeros((h, w), dtype=np.bool_)
    for x, y in tiles:
        mask[y, x] = True
    return mask


def _pockets(land: Land, label: list[list[int]], first: int) -> int:
    loose = {(x, y) for x, y in _land_tiles(land) if label[y][x] < 0}
    comp = components(loose)
    ids = {c: first + k for k, c in enumerate(sorted(set(comp.values())))}
    for (x, y), c in comp.items():
        label[y][x] = ids[c]
    return first + len(ids)


def home_gap(land: Land, anchors: Sequence[Tile], graph: PlaceGraph) -> float:
    """The least walkable distance between two home anchors over the side, infinite when no
    two homes share a land mass."""
    walk = frozenset(_land_tiles(land))
    homes = [anchors[i] for i, r in enumerate(graph.roles) if r == PlaceRole.HOME]
    gap = math.inf
    for k, a in enumerate(homes):
        d = distances(walk, [a], STEPS4)
        for b in homes[k + 1 :]:
            if b in d:
                gap = min(gap, d[b] / len(land))
    return gap


def grow(land: Land, graph: PlaceGraph, anchors: Sequence[Tile], rng: random.Random) -> Layout:
    """The regions grown from ``anchors`` and how well they realise ``graph``."""
    label = grow_regions(land, anchors, graph.sizes, rng)
    places = _pockets(land, label, len(graph.roles))
    real = label_adjacency(label)
    homes = {i for i, r in enumerate(graph.roles) if r == PlaceRole.HOME}
    area = collections.Counter(z for row in label for z in row)
    return Layout(
        label,
        tuple(anchors),
        places,
        frozenset(graph.edges - real),
        sum(1 for a, b in real if a in homes and b in homes),
        home_gap(land, anchors, graph),
        sum(1 for h in homes if area[h] < min(HOME_FLOOR, graph.sizes[h])),
    )


def nudge(points: Sequence[Point], layout: Layout) -> list[Point]:
    """``points`` with the two ends of every missing edge drawn ``NUDGE`` of the way toward
    each other."""
    pts = [list(p) for p in points]
    for a, b in sorted(layout.missing):
        dx, dy = pts[b][0] - pts[a][0], pts[b][1] - pts[a][1]
        pts[a][0] += NUDGE * dx / 2
        pts[a][1] += NUDGE * dy / 2
        pts[b][0] -= NUDGE * dx / 2
        pts[b][1] -= NUDGE * dy / 2
    return [(p[0], p[1]) for p in pts]


def _score(layout: Layout, target_gap: float) -> tuple[int, float, int]:
    return (
        layout.starved + layout.home_contacts,
        max(0.0, target_gap - layout.home_gap),
        len(layout.missing),
    )


def _order(graph: PlaceGraph) -> list[int]:
    return sorted(
        range(len(graph.roles)),
        key=lambda i: (graph.roles[i] != PlaceRole.HOME, -graph.sizes[i], i),
    )


def lay_out(land: Land, graph: PlaceGraph, target_gap: float, rng: random.Random) -> Layout:
    """The best of up to ``TRIES`` growths, each from the last one's anchors nudged toward
    its missing edges. Every anchor stands on the largest land mass. Homes start
    ``target_gap`` of the side apart and snap first, each where a square of its floor area
    is nearly all land. A layout
    scores by starved homes and home contacts, then by how far the homes fall short of
    ``target_gap``, then by missing edges."""
    n_land = len(_land_tiles(land))
    gap = SPREAD * math.sqrt(n_land / len(graph.roles))
    homes = [i for i, r in enumerate(graph.roles) if r == PlaceRole.HOME]
    home_apart = target_gap * len(land)
    order = _order(graph)
    mass = main_land(land)
    room = roomy(mass, math.ceil(math.sqrt(HOME_FLOOR)))
    rooms = {h: room for h in homes}
    points = fit_to_land(classical_scaling(graph_distances(graph)), mass, rng)
    points = spread(separate(points, homes, home_apart, mass), gap)
    best: Layout | None = None
    for _ in range(TRIES):
        layout = grow(land, graph, snap(points, mass, order, SNAP_GAP * gap, rooms), rng)
        if best is None or _score(layout, target_gap) < _score(best, target_gap):
            best = layout
        if _score(best, target_gap) == (0, 0.0, 0):
            break
        points = separate(nudge(points, layout), homes, home_apart, mass)
    if best is None:
        raise ValueError("lay_out needs at least one try")
    return best

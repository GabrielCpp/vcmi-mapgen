"""Paint readings of one level (map-math 1.6): the depth of every tile from the border it
faces, the transition bands, the raw-cut length, the dominant share per place, the accents
and the accent locality violations. Every function reads a terrain grid and a place label
grid, both ``[y][x]``, with label -1 off land."""

import collections
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.grid.reach import STEPS4
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.reading.borders import Pair

type Terrains = Sequence[Sequence[Terrain]]
type Labels = Sequence[Sequence[int]]

MAX_DEPTH = 6
PURE = 0.1
MIN_LEVEL = 3


@dataclass(frozen=True, slots=True)
class Accent:
    """One accent: its place, its terrain and its tile count."""

    place: int
    terrain: Terrain
    size: int


@dataclass(frozen=True, slots=True)
class PaintReading:
    """The paint invariants of one level. ``raw_cut`` counts the land pairs that change
    terrain outside every excused tile, ``border`` counts the land pairs that change place,
    ``shares`` holds each place's dominant share, and ``violations`` counts the non-dominant
    components that meet another place outside the excused tiles."""

    raw_cut: int
    border: int
    shares: Mapping[int, float]
    violations: int


def _neighbours(label: Labels, x: int, y: int) -> list[Tile]:
    H, W = len(label), len(label[0])
    return [(x + dx, y + dy) for dx, dy in STEPS4 if 0 <= x + dx < W and 0 <= y + dy < H]


def pair(a: int, b: int) -> Pair:
    return (a, b) if a < b else (b, a)


def boundary_tiles(label: Labels) -> frozenset[Tile]:
    """The labelled tiles with a 4-neighbour in another place."""
    return frozenset(
        (x, y)
        for y, row in enumerate(label)
        for x, z in enumerate(row)
        if z >= 0 and any(label[ny][nx] not in (-1, z) for nx, ny in _neighbours(label, x, y))
    )


def border_depth(label: Labels, pairs: Collection[Pair]) -> dict[Tile, tuple[int, int]]:
    """Each tile of a place ``p`` reachable inside its place from a border with some ``q``,
    ``(p, q)`` sorted in ``pairs``, mapped to its 4-step distance from the nearest tile of
    ``p`` touching such a ``q`` and to that ``q``. A tile touching several takes the
    lowest ``q``."""
    wanted = set(pairs)
    out: dict[Tile, tuple[int, int]] = {}
    frontier: list[Tile] = []
    for y, row in enumerate(label):
        for x, z in enumerate(row):
            if z < 0:
                continue
            faced = [
                label[ny][nx]
                for nx, ny in _neighbours(label, x, y)
                if label[ny][nx] not in (-1, z) and pair(z, label[ny][nx]) in wanted
            ]
            if faced:
                out[(x, y)] = (0, min(faced))
                frontier.append((x, y))
    while frontier:
        nxt: list[Tile] = []
        for x, y in frontier:
            d, q = out[(x, y)]
            for nx, ny in _neighbours(label, x, y):
                if label[ny][nx] == label[y][x] and (nx, ny) not in out:
                    out[(nx, ny)] = (d + 1, q)
                    nxt.append((nx, ny))
        frontier = nxt
    return out


def half_depth(width: int) -> int:
    """The band depth on each side of a border whose transition is ``width`` levels wide."""
    return (width + 1) // 2


def band_tiles(
    label: Labels, depth: Mapping[Tile, tuple[int, int]], widths: Mapping[Pair, int]
) -> frozenset[Tile]:
    """The tiles closer than ``max(1, w)`` to the border they face, ``w`` the width of that
    border in ``widths``. A border missing from ``widths`` has no band."""
    out: set[Tile] = set()
    for (x, y), (d, q) in depth.items():
        w = widths.get(pair(label[y][x], q))
        if w is not None and d < max(1, w):
            out.add((x, y))
    return frozenset(out)


def raw_cut(terrain: Terrains, excused: Collection[Tile]) -> int:
    """The 4-adjacent land pairs of different terrain with neither tile excused."""
    H, W = len(terrain), len(terrain[0])
    cut = 0
    for y in range(H):
        for x in range(W):
            t = terrain[y][x]
            if not t.is_land or (x, y) in excused:
                continue
            for nx, ny in ((x + 1, y), (x, y + 1)):
                if nx < W and ny < H:
                    u = terrain[ny][nx]
                    cut += u.is_land and u != t and (nx, ny) not in excused
    return cut


def border_length(label: Labels) -> int:
    """The 4-adjacent pairs of labelled tiles in different places."""
    H, W = len(label), len(label[0])
    return sum(
        1
        for y in range(H)
        for x in range(W)
        for nx, ny in ((x + 1, y), (x, y + 1))
        if nx < W and ny < H and label[y][x] >= 0 and label[ny][nx] not in (-1, label[y][x])
    )


def dominant_shares(
    terrain: Terrains, label: Labels, dominant: Mapping[int, Terrain]
) -> dict[int, float]:
    """Each place's share of tiles in its dominant terrain."""
    area: collections.Counter[int] = collections.Counter()
    hits: collections.Counter[int] = collections.Counter()
    for row_t, row_z in zip(terrain, label, strict=True):
        for t, z in zip(row_t, row_z, strict=True):
            if z >= 0:
                area[z] += 1
                hits[z] += t == dominant[z]
    return {z: hits[z] / area[z] for z in sorted(area)}


def components(tiles: Collection[Tile], same: Mapping[Tile, int]) -> list[list[Tile]]:
    """The 4-connected components of ``tiles`` whose tiles share their ``same`` value, each
    starting from its lowest tile."""
    seen: set[Tile] = set()
    out: list[list[Tile]] = []
    pool = set(tiles)
    for start in sorted(pool):
        if start in seen:
            continue
        seen.add(start)
        stack, comp = [start], [start]
        while stack:
            x, y = stack.pop()
            for dx, dy in STEPS4:
                n = (x + dx, y + dy)
                if n in pool and n not in seen and same[n] == same[start]:
                    seen.add(n)
                    stack.append(n)
                    comp.append(n)
        out.append(comp)
    return out


def off_dominant(
    terrain: Terrains, label: Labels, dominant: Mapping[int, Terrain]
) -> dict[Tile, int]:
    """Each labelled tile off its place's dominant terrain, mapped to its place."""
    return {
        (x, y): z
        for y, row in enumerate(label)
        for x, z in enumerate(row)
        if z >= 0 and terrain[y][x] != dominant[z]
    }


def accent_violations(
    terrain: Terrains, label: Labels, dominant: Mapping[int, Terrain], excused: Collection[Tile]
) -> int:
    """The 4-connected components of tiles off their place's dominant terrain that meet a
    tile touching another place outside ``excused``."""
    off = off_dominant(terrain, label, dominant)
    edge = boundary_tiles(label)
    one = dict.fromkeys(off, 0)
    return sum(
        1 for comp in components(off, one) if any(t in edge and t not in excused for t in comp)
    )


def accents(terrain: Terrains, label: Labels, dominant: Mapping[int, Terrain]) -> list[Accent]:
    """The same-terrain components off their place's dominant terrain that stay inside one
    place and touch no other place."""
    off = off_dominant(terrain, label, dominant)
    key = {(x, y): z * 16 + terrain[y][x] for (x, y), z in off.items()}
    edge = boundary_tiles(label)
    return [
        Accent(off[comp[0]], terrain[comp[0][1]][comp[0][0]], len(comp))
        for comp in components(off, key)
        if not any(t in edge for t in comp)
    ]


def transition_width(
    terrain: Terrains, label: Labels, depth: Mapping[Tile, tuple[int, int]], pq: Pair, d: Pair
) -> int:
    """The depth levels on either side of the border ``pq``, whose places have dominants
    ``d``, holding at least ``MIN_LEVEL`` tiles of the two terrains, in which the other
    side's terrain takes a share strictly between ``PURE`` and ``1 - PURE``."""
    p, q = pq
    other = {p: d[1], q: d[0]}
    mine = {p: d[0], q: d[1]}
    total: collections.Counter[tuple[int, int]] = collections.Counter()
    crossed: collections.Counter[tuple[int, int]] = collections.Counter()
    for (x, y), (k, faced) in depth.items():
        z = label[y][x]
        if k >= MAX_DEPTH or pair(z, faced) != pq:
            continue
        t = terrain[y][x]
        if t in (mine[z], other[z]):
            total[z, k] += 1
            crossed[z, k] += t == other[z]
    return sum(
        1 for level, n in total.items() if n >= MIN_LEVEL and PURE < crossed[level] / n < 1 - PURE
    )


def read_paint(
    terrain: Terrains, label: Labels, dominant: Mapping[int, Terrain], excused: Collection[Tile]
) -> PaintReading:
    """The paint invariants of one level, ``excused`` being its barrier and transition
    tiles."""
    return PaintReading(
        raw_cut=raw_cut(terrain, excused),
        border=border_length(label),
        shares=dominant_shares(terrain, label, dominant),
        violations=accent_violations(terrain, label, dominant, excused),
    )

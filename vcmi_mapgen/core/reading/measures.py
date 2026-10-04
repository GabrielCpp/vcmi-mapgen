"""Functionals of an inferred place map that the corpus statistics pool (map-math 3.4):
shape, home separation, border kind, barrier depth, transition widths and the raw-cut
share."""

import itertools
import math
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from vcmi_mapgen.core.grid.reach import STEPS4, distances
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.reading.borders import MERGE_BARRIER, Edge, Pair, barrier_fraction
from vcmi_mapgen.core.reading.ground import Ground
from vcmi_mapgen.core.reading.paint import (
    band_tiles,
    border_depth,
    border_length,
    half_depth,
    pair,
    raw_cut,
    transition_width,
)
from vcmi_mapgen.core.reading.places import Border, InferredPlaces, Place, PlaceRole


class BorderKind(StrEnum):
    BARRIER = "barrier"
    TRANSITION = "transition"
    RAW_CUT = "raw_cut"


def regions(inferred: InferredPlaces) -> dict[int, frozenset[Tile]]:
    """Place id -> its tiles."""
    out: dict[int, set[Tile]] = {}
    for y, row in enumerate(inferred.labels):
        for x, lab in enumerate(row):
            if lab >= 0:
                out.setdefault(lab, set()).add((x, y))
    return {lab: frozenset(tiles) for lab, tiles in sorted(out.items())}


def compactness(place: Place) -> float:
    """``|boundary|^2 / |R|``."""
    return place.boundary**2 / place.area


def _cross(o: Tile, a: Tile, b: Tile) -> int:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def hull(tiles: Collection[Tile]) -> list[Tile]:
    """The convex hull of the tile centres, counter-clockwise, by the monotone chain."""
    pts = sorted(set(tiles))
    if len(pts) <= 2:
        return pts
    lower: list[Tile] = []
    upper: list[Tile] = []
    for p in pts:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], p) <= 0:
            _ = lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], p) <= 0:
            _ = upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def perimeter(points: Sequence[Tile]) -> float:
    """The length of the closed polygon through ``points``."""
    if len(points) < 2:
        return 0.0
    return sum(math.dist(a, b) for a, b in itertools.pairwise([*points, points[0]]))


def roughness(place: Place, tiles: Collection[Tile]) -> float:
    """The boundary tile count over the perimeter of the convex hull of the tile centres,
    1 for a filled rectangle."""
    return place.boundary / max(1.0, perimeter(hull(tiles)))


def home_separation(ground: Ground, inferred: InferredPlaces) -> list[float]:
    """The walkable geodesic distance between every pair of homes, over the map side.
    A pair with no walkable path between them is left out."""
    homes = [p.towns[0] for p in inferred.places if p.role == PlaceRole.HOME and p.towns]
    side = max(ground.width, ground.height)
    out: list[float] = []
    for i, a in enumerate(homes):
        d = distances(ground.walk, [a], STEPS4)
        out.extend(d[b] / side for b in homes[i + 1 :] if b in d)
    return out


def border_kind(ground: Ground, edges: Sequence[Edge]) -> BorderKind:
    """Barrier when more than half the pairs have a non-walkable side. Otherwise a
    transition when most walkable pairs change terrain, and a raw cut when they do not."""
    if barrier_fraction(ground, edges) > MERGE_BARRIER:
        return BorderKind.BARRIER
    walkable = [(u, v) for u, v in edges if u in ground.walk and v in ground.walk]
    changed = sum(
        1 for (ux, uy), (vx, vy) in walkable if ground.terrain[uy][ux] != ground.terrain[vy][vx]
    )
    return BorderKind.TRANSITION if 2 * changed > len(walkable) else BorderKind.RAW_CUT


def barrier_depth(ground: Ground, border: Border, both: frozenset[Tile]) -> float:
    """``|W| / |B|``: W is the blocked land of the two places ``both`` covers that is
    4-connected, through blocked land of the two places, to a blocked tile of the border."""
    blocked = ground.blocked & both
    start = sorted({t for e in border.edges for t in e if t in blocked})
    return len(distances(blocked, start, STEPS4)) / len(border.edges)


@dataclass(frozen=True, slots=True)
class SoftBorders:
    """The non-barrier borders between places of different dominants: each tile's depth
    from the border it faces and each border's transition width."""

    depth: Mapping[Tile, tuple[int, int]]
    widths: Mapping[Pair, int]


def soft_borders(ground: Ground, inferred: InferredPlaces) -> SoftBorders:
    """The depth and the transition width of every soft border of ``inferred``."""
    label = inferred.labels
    dominant = {p: place.dominant for p, place in enumerate(inferred.places)}
    soft = [
        pair(p, q)
        for (p, q), border in inferred.borders.items()
        if dominant[p] != dominant[q] and border_kind(ground, border.edges) != BorderKind.BARRIER
    ]
    depth = border_depth(label, soft)
    widths = {
        pq: transition_width(ground.terrain, label, depth, pq, (dominant[pq[0]], dominant[pq[1]]))
        for pq in soft
    }
    return SoftBorders(depth, widths)


def raw_cut_share(ground: Ground, inferred: InferredPlaces, soft: SoftBorders) -> float | None:
    """The raw-cut length outside the transition bands and the blocked tiles over the total
    border length, None without a border."""
    label = inferred.labels
    border = border_length(label)
    if not border:
        return None
    bands = band_tiles(label, soft.depth, {pq: half_depth(w) for pq, w in soft.widths.items()})
    return raw_cut(ground.terrain, bands | ground.blocked) / border

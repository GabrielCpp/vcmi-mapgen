"""The places on land (map-math 4.2): regions grown from their anchors to their target
sizes, with every land mass no anchor reached as a pocket of its own, and the room test and
the walking gap the homes read."""

import collections
import math
import random
from collections.abc import Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.grid.components import components
from vcmi_mapgen.core.grid.reach import STEPS4, distances
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.steps.terrain_gen.macro import grow_regions

ROOM_FILL = 0.9

type Land = Sequence[Sequence[bool]]


@dataclass(frozen=True, slots=True)
class Layout:
    """``label[y][x]`` is the place of a land tile and -1 off land. Place ``i`` below
    ``len(anchors)`` grew from ``anchors[i]``. The places after them are pockets grown on
    land no anchor reached. ``places`` counts them all."""

    label: list[list[int]]
    anchors: tuple[Tile, ...]
    places: int


def _land_tiles(land: Land) -> list[Tile]:
    return [(x, y) for y, row in enumerate(land) for x, v in enumerate(row) if v]


def main_land(land: Land) -> list[list[bool]]:
    """The largest four-connected land mass of ``land``, the lowest-numbered on a tie."""
    comp = components(frozenset(_land_tiles(land)))
    sizes = collections.Counter(comp.values())
    keep = min(sizes, key=lambda c: (-sizes[c], c), default=-1)
    return [[comp.get((x, y)) == keep for x in range(len(row))] for y, row in enumerate(land)]


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


def _pockets(land: Land, label: list[list[int]], first: int) -> int:
    loose = {(x, y) for x, y in _land_tiles(land) if label[y][x] < 0}
    comp = components(loose)
    ids = {c: first + k for k, c in enumerate(sorted(set(comp.values())))}
    for (x, y), c in comp.items():
        label[y][x] = ids[c]
    return first + len(ids)


def home_gap(land: Land, points: Sequence[Tile]) -> float:
    """The least walkable distance between two of ``points`` over the side, infinite when no
    two of them share a land mass."""
    walk = frozenset(_land_tiles(land))
    gap = math.inf
    for k, a in enumerate(points):
        d = distances(walk, [a], STEPS4)
        for b in points[k + 1 :]:
            if b in d:
                gap = min(gap, d[b] / len(land))
    return gap


def grow(land: Land, anchors: Sequence[Tile], caps: Sequence[int], rng: random.Random) -> Layout:
    """The regions grown from ``anchors``, each up to its cap in ``caps``, then one pocket
    per piece of land no anchor reached."""
    label = grow_regions(land, anchors, caps, rng)
    places = _pockets(land, label, len(anchors))
    return Layout(label, tuple(anchors), places)

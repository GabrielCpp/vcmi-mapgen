"""The home places, chosen on the grown shapes: the roomy places of the largest land mass,
taken farthest-first by walking distance, and accepted once the homes stand the corpus gap
apart."""

import collections
import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.grid.reach import STEPS4, distances
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.steps.terrain_gen.layout import Layout, main_land, roomy
from vcmi_mapgen.core.steps.terrain_gen.place_draws import HOME_FLOOR
from vcmi_mapgen.core.steps.terrain_gen.place_map import label_adjacency

HOME_DRAWS = 12
"""How many first homes the choice tries before it settles for the best set."""


@dataclass(frozen=True, slots=True)
class Homes:
    """Player ``i`` is at home in place ``places[i]``, its town room centred on
    ``points[i]``. ``gap`` is the least walking distance between two points over the side,
    and ``crowded`` counts the home pairs that touch or share a neighbour."""

    places: tuple[int, ...]
    points: tuple[Tile, ...]
    gap: float
    crowded: int


def room_side() -> int:
    """The side of the square a home town needs, ``HOME_FLOOR`` tiles."""
    return math.ceil(math.sqrt(HOME_FLOOR))


def room_tiles(point: Tile, side: int) -> frozenset[Tile]:
    """The square of ``side`` tiles centred on ``point``."""
    h = side // 2
    x, y = point
    return frozenset((x + dx, y + dy) for dx in range(-h, h + 1) for dy in range(-h, h + 1))


def _centre(layout: Layout, place: int, tiles: Sequence[Tile]) -> Tile:
    if place < len(layout.anchors):
        cx, cy = layout.anchors[place]
    else:
        cx = sum(x for x, _ in tiles) / len(tiles)
        cy = sum(y for _, y in tiles) / len(tiles)
    return min(tiles, key=lambda t: ((t[0] - cx) ** 2 + (t[1] - cy) ** 2, t))


def home_points(layout: Layout) -> dict[int, Tile]:
    """The places a home fits in, each with its town point: the place's tile nearest its
    anchor whose square of ``room_side`` tiles is nearly all land. A place fits when it
    lies on the largest land mass, holds ``HOME_FLOOR`` tiles and has such a tile. Without
    one per player the caller falls back on ``fallback_points``."""
    land = [[z >= 0 for z in row] for row in layout.label]
    room = roomy(main_land(land), room_side())
    tiles: dict[int, list[Tile]] = collections.defaultdict(list)
    for y, row in enumerate(layout.label):
        for x, z in enumerate(row):
            if z >= 0:
                tiles[z].append((x, y))
    out: dict[int, Tile] = {}
    for p in sorted(tiles):
        roomy_tiles = [t for t in tiles[p] if t in room]
        if len(tiles[p]) >= HOME_FLOOR and roomy_tiles:
            out[p] = _centre(layout, p, roomy_tiles)
    return out


def fallback_points(layout: Layout) -> dict[int, Tile]:
    """Every place on the largest land mass with its tile nearest its anchor."""
    land = [[z >= 0 for z in row] for row in layout.label]
    mass = main_land(land)
    tiles: dict[int, list[Tile]] = collections.defaultdict(list)
    for y, row in enumerate(layout.label):
        for x, z in enumerate(row):
            if z >= 0 and mass[y][x]:
                tiles[z].append((x, y))
    return {p: _centre(layout, p, tiles[p]) for p in sorted(tiles)}


def _neighbours(layout: Layout) -> dict[int, set[int]]:
    out: dict[int, set[int]] = collections.defaultdict(set)
    for a, b in label_adjacency(layout.label):
        out[a].add(b)
        out[b].add(a)
    return out


def _crowded(a: int, b: int, nbr: Mapping[int, set[int]]) -> bool:
    return b in nbr[a] or bool(nbr[a] & nbr[b])


def _areas(layout: Layout) -> collections.Counter[int]:
    return collections.Counter(z for row in layout.label for z in row if z >= 0)


def choose_homes(layout: Layout, k: int, targets: tuple[float, float], rng: random.Random) -> Homes:
    """``k`` home places on ``layout``. ``targets`` holds the home gap over the side and
    the tiles a home territory grows toward. A home stands in a place no larger than that
    budget while ``k`` such places fit a home. Each draw starts from a random place a home
    fits in and adds the place farthest by walking from the homes so far, among the places
    that neither touch a home nor share a neighbour with one while such a place is left.
    The first draw whose homes stand the target gap apart with none crowded wins.
    Otherwise the draw with the fewest crowded pairs, then the widest gap, wins."""
    target_gap, budget = targets
    points = home_points(layout)
    if len(points) < k:
        points = fallback_points(layout) | points
    area = _areas(layout)
    fitting = sorted(p for p in points if area[p] <= budget)
    candidates = fitting if len(fitting) >= k else sorted(points)
    walk = frozenset(
        (x, y) for y, row in enumerate(layout.label) for x, z in enumerate(row) if z >= 0
    )
    side = len(layout.label)
    nbr = _neighbours(layout)
    memo: dict[int, dict[Tile, int]] = {}

    def apart(a: int, b: int) -> float:
        if a not in memo:
            memo[a] = distances(walk, [points[a]], STEPS4)
        return memo[a].get(points[b], math.inf)

    best: Homes | None = None
    for start in rng.sample(candidates, min(HOME_DRAWS, len(candidates))):
        chosen = [start]
        while len(chosen) < min(k, len(candidates)):
            left = [c for c in candidates if c not in chosen]
            pool = [c for c in left if not any(_crowded(c, h, nbr) for h in chosen)] or left
            chosen.append(max(pool, key=lambda c: (min(apart(h, c) for h in chosen), -c)))
        homes = sorted(chosen)
        gap = min(
            (apart(a, b) / side for i, a in enumerate(homes) for b in homes[i + 1 :]),
            default=math.inf,
        )
        crowded = sum(_crowded(a, b, nbr) for i, a in enumerate(homes) for b in homes[i + 1 :])
        drawn = Homes(tuple(homes), tuple(points[h] for h in homes), gap, crowded)
        if best is None or (drawn.crowded, -drawn.gap) < (best.crowded, -best.gap):
            best = drawn
        if crowded == 0 and gap >= target_gap:
            return drawn
    if best is None:
        return Homes((), (), math.inf, 0)
    return best

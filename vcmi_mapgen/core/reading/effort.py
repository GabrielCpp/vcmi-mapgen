"""How many days a hero needs to carry a reward home: the travel from the nearest home plus
the days spent beating the strongest guard on the way.

The route search walks the route map from every home at once. A step costs the day share of
the tile it leaves, √2 times that on a diagonal. Boarding a boat or landing from one ends the
day. A gate lets through only the hero holding its key, so each search follows one key
colour, picked up at that colour's tent. A search under a guard ceiling never enters a tile
a stronger guard covers. Effort at a tile is the cheapest of the toll of a ceiling plus the
days the search under that ceiling needs.
"""

from __future__ import annotations

import heapq
import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field

from vcmi_mapgen.core.reading.routes import RouteMap, Spot

DIAGONAL = math.sqrt(2)
_SLACK = 1e-9
_STEPS = tuple(
    (dx, dy, DIAGONAL if dx and dy else 1.0) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy
)


def _whole(days: float) -> int:
    return math.ceil(days - _SLACK)


@dataclass(frozen=True, slots=True)
class Effort:
    """The days a hero needs to reach a tile and the guard level it beats on the way."""

    days: int
    guard: int
    total: int


@dataclass(frozen=True, slots=True)
class _Flat:
    size: int
    levels: tuple[int, ...]
    cost: list[float]
    open: list[bool]
    water: list[bool]
    guard: list[int]
    gate: list[int]
    tent: list[int]
    dock: list[bool]
    jumps: dict[int, tuple[int, ...]]

    def index(self, spot: Spot) -> int:
        return (self.levels.index(spot.level) * self.size + spot.y) * self.size + spot.x


def _flat(route: RouteMap) -> _Flat:
    size, levels = route.size, tuple(route.levels())

    def flat[T](grids: dict[int, list[list[T]]]) -> list[T]:
        return [v for level in levels for row in grids[level] for v in row]

    out = _Flat(
        size=size,
        levels=levels,
        cost=[math.inf if c is None else c for c in flat(route.cost)],
        open=flat(route.open),
        water=flat(route.water),
        guard=flat(route.guard),
        gate=[-1] * (len(levels) * size * size),
        tent=[-1] * (len(levels) * size * size),
        dock=[False] * (len(levels) * size * size),
        jumps={},
    )
    for spot, channel in route.gates.items():
        out.gate[out.index(spot)] = channel
    for spot, channel in route.tents.items():
        out.tent[out.index(spot)] = channel
    for spot in route.docks:
        out.dock[out.index(spot)] = True
    for spot, landing in route.jumps.items():
        out.jumps[out.index(spot)] = tuple(out.index(s) for s in landing)
    return out


def _neighbours(size: int, tile: int) -> Iterator[tuple[int, float]]:
    rest, x = divmod(tile, size)
    base, y = divmod(rest, size)
    for dx, dy, scale in _STEPS:
        nx, ny = x + dx, y + dy
        if 0 <= nx < size and 0 <= ny < size:
            yield (base * size + ny) * size + nx, scale


@dataclass(slots=True)
class _Search:
    flat: _Flat
    ceiling: int
    colour: int
    best: list[float] = field(default_factory=list[float])
    heap: list[tuple[float, int]] = field(default_factory=list[tuple[float, int]])

    def reach(self, days: float, tile: int, key: int) -> None:
        if self.flat.tent[tile] == self.colour:
            key = 1
        state = tile * 4 + key * 2 + int(self.flat.water[tile])
        if days < self.best[state]:
            self.best[state] = days
            heapq.heappush(self.heap, (days, state))

    def passable(self, tile: int, key: int) -> bool:
        flat = self.flat
        if not flat.open[tile] or flat.guard[tile] > self.ceiling:
            return False
        return flat.gate[tile] < 0 or bool(key and flat.gate[tile] == self.colour)

    def arrive(self, days: float, tile: int, n: int, scale: float, boat: int) -> float | None:
        if boat == self.flat.water[n]:
            return days + self.flat.cost[tile] * scale
        if boat or self.flat.dock[n]:
            return math.floor(days + _SLACK) + 1.0
        return None

    def expand(self, days: float, state: int) -> None:
        tile, key, boat = state >> 2, (state >> 1) & 1, state & 1
        for n, scale in _neighbours(self.flat.size, tile):
            if not self.passable(n, key):
                continue
            arrive = self.arrive(days, tile, n, scale, boat)
            if arrive is None:
                continue
            self.reach(arrive, n, key)
            for far in self.flat.jumps.get(n, ()):
                if self.flat.guard[far] <= self.ceiling:
                    self.reach(arrive, far, key)


def _search(flat: _Flat, homes: Sequence[int], ceiling: int, colour: int) -> list[float]:
    tiles = len(flat.levels) * flat.size * flat.size
    run = _Search(flat, ceiling, colour, best=[math.inf] * (tiles * 4))
    for tile in homes:
        run.best[tile * 4] = 0.0
        run.heap.append((0.0, tile * 4))
    heapq.heapify(run.heap)
    while run.heap:
        days, state = heapq.heappop(run.heap)
        if days <= run.best[state]:
            run.expand(days, state)
    return [min(run.best[t * 4 : t * 4 + 4]) for t in range(tiles)]


@dataclass(frozen=True, slots=True)
class EffortMap:
    """The best travel days to every tile under each guard ceiling, and the toll of each
    ceiling. `at` reads a tile's effort."""

    flat: _Flat
    days: dict[int, list[float]]
    toll: Sequence[int]

    def at(self, spot: Spot) -> Effort | None:
        tile = self.flat.index(spot)
        options = [
            (self.toll[ceiling] + _whole(days[tile]), ceiling, _whole(days[tile]))
            for ceiling, days in self.days.items()
            if days[tile] < math.inf
        ]
        if not options:
            return None
        total, guard, days = min(options)
        return Effort(days=days, guard=guard, total=total)


def effort_map(route: RouteMap, homes: Sequence[Spot], toll: Sequence[int]) -> EffortMap:
    """The effort map from ``homes`` over ``route``. ``toll[level]`` is the days a hero needs
    to beat a guard of that level, with ``toll[0]`` zero."""
    flat = _flat(route)
    sources = [flat.index(h) for h in homes]
    colours = sorted(set(route.gates.values())) or [-2]
    days: dict[int, list[float]] = {}
    for ceiling in [0, *route.guard_levels()]:
        runs = [_search(flat, sources, ceiling, colour) for colour in colours]
        days[ceiling] = [min(col) for col in zip(*runs, strict=True)]
    return EffortMap(flat=flat, days=days, toll=toll)

"""Which starts reach a rival only by sea, and which shipyard links them. A hero walks the land
from beside its town under a guard ceiling, with every gate shut and every jump ignored. A sea
is one body of open water, its tiles joined on all eight sides. A hero boards a sea at a dock
beside open land, and lands from a sea on any open tile of a land beside it. Two players are
linked when a sea holds a dock beside the first one's land and touches the second one's land."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable, Iterator, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field

from vcmi_mapgen.core.reading.effort import EffortMap
from vcmi_mapgen.core.reading.routes import RouteMap, Spot
from vcmi_mapgen.core.steps.gameplay.shipyards import Boarding


def _around(route: RouteMap, spot: Spot) -> Iterator[Spot]:
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            x, y = spot.x + dx, spot.y + dy
            if (dx or dy) and 0 <= x < route.size and 0 <= y < route.size:
                yield Spot(spot.level, x, y)


def _ashore(route: RouteMap, spot: Spot) -> bool:
    return route.open[spot.level][spot.y][spot.x] and not route.water[spot.level][spot.y][spot.x]


def _afloat(route: RouteMap, spot: Spot) -> bool:
    return route.open[spot.level][spot.y][spot.x] and route.water[spot.level][spot.y][spot.x]


def walked(route: RouteMap, starts: Iterable[Spot], ceiling: int) -> frozenset[Spot]:
    """The land a hero walks from beside ``starts`` past no guard above ``ceiling``."""

    def free(s: Spot) -> bool:
        return (
            _ashore(route, s) and route.guard[s.level][s.y][s.x] <= ceiling and s not in route.gates
        )

    seen = {n for s in starts for n in (s, *_around(route, s)) if free(n)}
    todo = deque(sorted(seen, key=lambda s: (s.level, s.y, s.x)))
    while todo:
        for n in _around(route, todo.popleft()):
            if n not in seen and free(n):
                seen.add(n)
                todo.append(n)
    return frozenset(seen)


def seas(route: RouteMap) -> dict[Spot, int]:
    """The sea each open water tile belongs to, numbered from zero."""
    sea_of: dict[Spot, int] = {}
    label = 0
    for level in route.levels():
        for y in range(route.size):
            for x in range(route.size):
                start = Spot(level, x, y)
                if start in sea_of or not _afloat(route, start):
                    continue
                sea_of[start] = label
                todo = deque([start])
                while todo:
                    for n in _around(route, todo.popleft()):
                        if n not in sea_of and _afloat(route, n):
                            sea_of[n] = label
                            todo.append(n)
                label += 1
    return sea_of


def touched(route: RouteMap, sea_of: dict[Spot, int], land: AbstractSet[Spot]) -> frozenset[int]:
    """The seas a hero lands from onto ``land``."""
    return frozenset(sea_of[n] for s in land for n in _around(route, s) if n in sea_of)


def boarded(route: RouteMap, sea_of: dict[Spot, int], land: AbstractSet[Spot]) -> frozenset[int]:
    """The seas a hero on ``land`` boards at a dock."""
    return frozenset(
        sea_of[d] for d in route.docks if d in sea_of and any(n in land for n in _around(route, d))
    )


@dataclass(slots=True)
class SeaLinks:
    """The lands and seas of one route map, read from each player's town tiles."""

    route: RouteMap
    homes: Sequence[Sequence[Spot]]
    sea_of: dict[Spot, int] = field(default_factory=dict[Spot, int])
    _land: dict[tuple[int, int], frozenset[Spot]] = field(
        default_factory=dict[tuple[int, int], frozenset[Spot]]
    )

    def __post_init__(self) -> None:
        self.sea_of = seas(self.route)

    @property
    def top(self) -> int:
        return max(self.route.guard_levels(), default=0)

    def land(self, player: int, ceiling: int | None = None) -> frozenset[Spot]:
        """The land ``player`` walks from its town under ``ceiling``, every guard by default."""
        key = (player, self.top if ceiling is None else ceiling)
        if key not in self._land:
            self._land[key] = walked(self.route, self.homes[player], key[1])
        return self._land[key]

    def joined(self, a: int, b: int) -> bool:
        """Whether ``a`` walks to ``b``."""
        return not self.land(a).isdisjoint(self.land(b))

    def linked(self, a: int, b: int) -> bool:
        """Whether ``a`` boards a sea that lands it on ``b``'s land."""
        reach = touched(self.route, self.sea_of, self.land(b))
        return not boarded(self.route, self.sea_of, self.land(a)).isdisjoint(reach)

    def apart(self) -> list[tuple[int, int]]:
        """Every ordered pair of players apart by land."""
        n = len(self.homes)
        return [(a, b) for a in range(n) for b in range(n) if a != b and not self.joined(a, b)]

    def unlinked(self) -> list[tuple[int, int]]:
        """Every ordered pair of players apart by land and by sea."""
        return [(a, b) for a, b in self.apart() if not self.linked(a, b)]

    def fit(self, b: int, home: AbstractSet[Spot]) -> Callable[[Boarding], bool]:
        """Whether a hero boards at a dock from a tile of ``home`` onto a sea that lands it on
        ``b``'s land."""
        reach = touched(self.route, self.sea_of, self.land(b))

        def ok(boarding: Boarding) -> bool:
            dock, shore = boarding
            sea = self.sea_of.get(Spot(0, *dock))
            return sea in reach and Spot(0, *shore) in home

        return ok


def sea_way(em: EffortMap, doors: Sequence[Spot]) -> list[Spot]:
    """The tiles a hero walks and sails to the cheapest of ``doors``, home first. Empty when
    it reaches none."""
    priced = [(e.total, i) for i, d in enumerate(doors) if (e := em.visit(d)) is not None]
    return em.way(doors[min(priced)[1]]) if priced else []

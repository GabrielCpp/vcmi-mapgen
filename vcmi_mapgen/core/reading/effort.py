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
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import cast

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.reading.effort_search import SLACK, STEPS, Grid, search
from vcmi_mapgen.core.reading.routes import RouteMap, Spot

_MATCH = 1e-6
AROUND = 3
UNREACHED = -1


def _whole(days: float) -> int:
    return math.ceil(days - SLACK)


@dataclass(frozen=True, slots=True)
class Effort:
    """The days a hero needs to reach a tile and the guard level it beats on the way."""

    days: int
    guard: int
    total: int


@dataclass(frozen=True, slots=True)
class _Flat:
    grid: Grid
    levels: tuple[int, ...]
    jumps: dict[int, tuple[int, ...]]

    @property
    def size(self) -> int:
        return self.grid.size

    def index(self, spot: Spot) -> int:
        return (self.levels.index(spot.level) * self.size + spot.y) * self.size + spot.x

    def spot(self, tile: int) -> Spot:
        rest, x = divmod(tile, self.size)
        level, y = divmod(rest, self.size)
        return Spot(self.levels[level], x, y)


def _flat(route: RouteMap) -> _Flat:
    size, levels = route.size, tuple(route.levels())
    tiles = len(levels) * size * size

    def flat[T](grids: dict[int, list[list[T]]]) -> list[T]:
        return [v for level in levels for row in grids[level] for v in row]

    def index(spot: Spot) -> int:
        return (levels.index(spot.level) * size + spot.y) * size + spot.x

    gate = np.full(tiles, -1, dtype=np.int64)
    tent = np.full(tiles, -1, dtype=np.int64)
    dock = np.zeros(tiles, dtype=np.bool_)
    for spot, channel in route.gates.items():
        gate[index(spot)] = channel
    for spot, channel in route.tents.items():
        tent[index(spot)] = channel
    for spot in route.docks:
        dock[index(spot)] = True
    jumps = {index(spot): tuple(index(s) for s in landing) for spot, landing in route.jumps.items()}
    counts = np.zeros(tiles + 1, dtype=np.int64)
    for tile, landing in jumps.items():
        counts[tile + 1] = len(landing)
    jump_at = np.cumsum(counts)
    jump_to = np.zeros(jump_at.item(-1), dtype=np.int64)
    for tile, landing in jumps.items():
        jump_to[jump_at.item(tile) : jump_at.item(tile + 1)] = landing
    grid = Grid(
        size=size,
        cost=np.array([math.inf if c is None else c for c in flat(route.cost)], dtype=np.float64),
        open=np.array(flat(route.open), dtype=np.bool_),
        water=np.array(flat(route.water), dtype=np.bool_),
        guard=np.array(flat(route.guard), dtype=np.int64),
        gate=gate,
        tent=tent,
        dock=dock,
        jump_at=jump_at,
        jump_to=jump_to,
    )
    return _Flat(grid=grid, levels=levels, jumps=jumps)


def _neighbours(size: int, tile: int) -> Iterator[tuple[int, float]]:
    rest, x = divmod(tile, size)
    base, y = divmod(rest, size)
    for dx, dy, scale in STEPS:
        nx, ny = x + dx, y + dy
        if 0 <= nx < size and 0 <= ny < size:
            yield (base * size + ny) * size + nx, scale


def _search(flat: _Flat, homes: Sequence[int], ceiling: int, colour: int) -> NDArray[np.float64]:
    best = search(flat.grid, np.array(homes, dtype=np.int64), ceiling, colour)
    return cast(NDArray[np.float64], best.reshape(-1, 4).min(axis=1))


@dataclass(frozen=True, slots=True)
class EffortMap:
    """The best travel days to every tile under each guard ceiling, and the toll of each
    ceiling. `at` reads a tile's effort."""

    flat: _Flat
    days: dict[int, NDArray[np.float64]]
    toll: Sequence[int]

    def at(self, spot: Spot, least: int = 0) -> Effort | None:
        """The effort to reach ``spot``, beating a guard of at least ``least`` on the way."""
        best = self._cheapest([self.flat.index(spot)], least)
        return None if best is None else best[0]

    def beside(self, spot: Spot, least: int, shut: AbstractSet[Spot]) -> Effort | None:
        """The effort to reach ``spot`` once an object blocks ``shut``, beating a guard of at
        least ``least`` on the way. The tiles within ``AROUND`` steps of ``spot`` are walked
        again around ``shut``. The days beyond them stand."""
        tile = self.flat.index(spot)
        blocked = {self.flat.index(s) for s in shut if s.level == spot.level}
        options: list[tuple[int, int, int]] = []
        for ceiling, days in self.days.items():
            if any(ceiling < c <= least for c in self.days):
                continue
            arrive = _around(self.flat, days, ceiling, tile, blocked)
            if arrive < math.inf:
                guard = max(ceiling, least)
                options.append((self.toll[guard] + _whole(arrive), guard, _whole(arrive)))
        if not options:
            return None
        total, guard, whole = min(options)
        return Effort(days=whole, guard=guard, total=total)

    def visit(self, door: Spot, least: int = 0) -> Effort | None:
        """The effort to visit the object whose entrance is ``door``: a hero steps on it from
        an open tile beside it and beats the guard covering ``door`` on the way, and a guard
        of at least ``least``."""
        guard = max(self.flat.grid.guard.item(self.flat.index(door)), least)
        best = self._cheapest(self._sides(door), guard)
        return None if best is None else best[0]

    def visits(self, doors: Sequence[Spot], top: int) -> NDArray[np.int64]:
        """Per guard level 0..``top`` and per door, the total days `visit` gives with that
        level as ``least``, UNREACHED where no home reaches the door."""
        flat = self.flat
        shape = (len(flat.levels), flat.size, flat.size)
        index = np.array([flat.index(d) for d in doors], dtype=np.intp)
        toll = np.array(self.toll, dtype=np.float64)
        door_guard = np.array(flat.grid.guard, dtype=np.intp)[index]
        out = np.full((top + 1, len(doors)), np.inf)
        for ceiling, days in self.days.items():
            near = _beside(np.array(days, dtype=np.float64).reshape(shape)).reshape(-1)[index]
            whole = np.ceil(near - SLACK)
            for least in range(top + 1):
                guard = np.maximum(np.maximum(door_guard, least), ceiling)
                out[least] = np.minimum(cast(NDArray[np.float64], out[least]), toll[guard] + whole)
        return np.where(np.isfinite(out), out, UNREACHED).astype(np.int64)

    def way(self, door: Spot) -> list[Spot]:
        """The tiles a hero walks from the nearest home to the tile beside ``door`` it visits
        from, home first, under the guard ceiling `visit` prices. Empty when no home reaches
        ``door``."""
        return self._walk(
            self._cheapest(self._sides(door), self.flat.grid.guard.item(self.flat.index(door)))
        )

    def path(self, spot: Spot) -> list[Spot]:
        """The tiles a hero walks from the nearest home to ``spot``, home first, under the
        guard ceiling `at` prices. Empty when no home reaches ``spot``."""
        return self._walk(self._cheapest([self.flat.index(spot)], 0))

    def _walk(self, best: tuple[Effort, int, int] | None) -> list[Spot]:
        if best is None:
            return []
        _effort, ceiling, tile = best
        return [self.flat.spot(t) for t in reversed(_descend(self.flat, self.days[ceiling], tile))]

    def _sides(self, door: Spot) -> list[int]:
        size = self.flat.size
        return [
            self.flat.index(Spot(door.level, door.x + dx, door.y + dy))
            for dx, dy, _ in STEPS
            if 0 <= door.x + dx < size and 0 <= door.y + dy < size
        ]

    def _cheapest(self, tiles: Sequence[int], least: int) -> tuple[Effort, int, int] | None:
        options = [
            (
                self.toll[max(ceiling, least)] + _whole(days.item(tile)),
                max(ceiling, least),
                _whole(days.item(tile)),
                ceiling,
                tile,
            )
            for ceiling, days in self.days.items()
            for tile in tiles
            if days.item(tile) < math.inf
        ]
        if not options:
            return None
        total, guard, days, ceiling, tile = min(options)
        return Effort(days=days, guard=guard, total=total), ceiling, tile


def _beside(days: NDArray[np.float64]) -> NDArray[np.float64]:
    padded = np.pad(days, ((0, 0), (1, 1), (1, 1)), constant_values=np.inf)
    _levels, rows, cols = days.shape
    best = np.full(days.shape, np.inf)
    for dx, dy, _scale in STEPS:
        best = np.minimum(best, padded[:, 1 + dy : 1 + dy + rows, 1 + dx : 1 + dx + cols])
    return best


def _around(
    flat: _Flat, days: NDArray[np.float64], ceiling: int, tile: int, shut: set[int]
) -> float:
    rest, x = divmod(tile, flat.size)
    base, y = divmod(rest, flat.size)
    near = {
        (base * flat.size + ny) * flat.size + nx
        for ny in range(max(0, y - AROUND), min(flat.size, y + AROUND + 1))
        for nx in range(max(0, x - AROUND), min(flat.size, x + AROUND + 1))
    }
    best = dict.fromkeys(near, math.inf)
    heap: list[tuple[float, int]] = []
    for t in near:
        nx, ny = t % flat.size, t // flat.size % flat.size
        edge = max(abs(nx - x), abs(ny - y)) == AROUND or days.item(t) <= SLACK
        if edge and t not in shut and days.item(t) < math.inf:
            best[t] = days.item(t)
            heap.append((days.item(t), t))
    heapq.heapify(heap)
    while heap:
        d, t = heapq.heappop(heap)
        if d > best[t]:
            continue
        for n, scale in _neighbours(flat.size, t):
            if (
                n not in near
                or n in shut
                or not flat.grid.open.item(n)
                or flat.grid.guard.item(n) > ceiling
            ):
                continue
            same = flat.grid.water.item(n) == flat.grid.water.item(t)
            arrive = d + flat.grid.cost.item(t) * scale if same else math.floor(d + SLACK) + 1.0
            if arrive < best[n]:
                best[n] = arrive
                heapq.heappush(heap, (arrive, n))
    return best[tile]


def _before(
    flat: _Flat, days: NDArray[np.float64], tile: int, landed: dict[int, list[int]]
) -> int | None:
    here = days.item(tile)
    lower = [
        (days.item(n), n, scale) for n, scale in _neighbours(flat.size, tile) if days.item(n) < here
    ]
    for d, n, scale in sorted(lower):
        if flat.grid.water.item(n) == flat.grid.water.item(tile):
            if abs(d + flat.grid.cost.item(n) * scale - here) <= _MATCH:
                return n
        elif abs(math.floor(d + SLACK) + 1.0 - here) <= _MATCH:
            return n
    jumped = [n for n in landed.get(tile, ()) if abs(days.item(n) - here) <= _MATCH]
    if jumped:
        return min(jumped)
    return min(lower)[1] if lower else None


def _descend(flat: _Flat, days: NDArray[np.float64], tile: int) -> list[int]:
    landed: dict[int, list[int]] = {}
    for src, ends in flat.jumps.items():
        for end in ends:
            landed.setdefault(end, []).append(src)
    path = [tile]
    seen = {tile}
    while days.item(tile) > SLACK:
        prev = _before(flat, days, tile, landed)
        if prev is None or prev in seen:
            break
        path.append(prev)
        seen.add(prev)
        tile = prev
    return path


def effort_map(route: RouteMap, homes: Sequence[Spot], toll: Sequence[int]) -> EffortMap:
    """The effort map from ``homes`` over ``route``. ``toll[level]`` is the days a hero needs
    to beat a guard of that level, with ``toll[0]`` zero."""
    flat = _flat(route)
    sources = [flat.index(h) for h in homes]
    colours = sorted(set(route.gates.values())) or [-2]
    days: dict[int, NDArray[np.float64]] = {}
    for ceiling in [0, *route.guard_levels()]:
        runs = [_search(flat, sources, ceiling, colour) for colour in colours]
        days[ceiling] = np.minimum.reduce(runs)
    return EffortMap(flat=flat, days=days, toll=toll)

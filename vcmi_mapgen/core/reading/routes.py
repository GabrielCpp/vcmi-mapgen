"""The ground a hero crosses on the way to a reward, read from a generated or a corpus map.

A tile is open when its terrain lets a hero stand and no lasting object blocks it. An object
the catalog calls vanishing, a pickup or a monster, leaves when the hero meets it, so its
tiles stay open. A lasting object closes its visit tile, and a hero visits it from a
neighbouring tile. Water is open only to a hero afloat. A crossing changes what the hero
holds or where it stands: a tent hands its key, a gate lets through only that key, a
teleport, a one-way monolith or a subterranean gate moves the hero to its twin, and the
water beside a shipyard or under a boat is where the hero boards. A monster guards its own
tile and the eight around it that share its ground, land or water.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vcmi_mapgen.core.catalog import Catalog, Crossing, HeroPace
from vcmi_mapgen.core.model import MapState, PlacedObject
from vcmi_mapgen.core.model.terrain import Terrain

_JUMPS = frozenset({Crossing.TELEPORT, Crossing.ONE_WAY_IN, Crossing.UNDERGROUND})
_PASSED = frozenset({Crossing.GATE, Crossing.TENT, *_JUMPS})


@dataclass(frozen=True, slots=True)
class Spot:
    """One tile on one level."""

    level: int
    x: int
    y: int


@dataclass(frozen=True, slots=True)
class RouteMap:
    """Per level, the day share one straight step leaving each tile costs, None on rock,
    whether a hero may enter the tile, whether it is water, and the strongest guard whose
    zone covers it. `gates`
    and `tents` give the key channel at each gate and tent tile, `docks` the water tiles a
    hero boards at, and `jumps` the tiles a hero stepping onto a tile lands on instead."""

    size: int
    cost: dict[int, list[list[float | None]]]
    open: dict[int, list[list[bool]]]
    water: dict[int, list[list[bool]]]
    guard: dict[int, list[list[int]]]
    gates: dict[Spot, int] = field(default_factory=dict)
    tents: dict[Spot, int] = field(default_factory=dict)
    docks: frozenset[Spot] = frozenset()
    jumps: dict[Spot, tuple[Spot, ...]] = field(default_factory=dict)

    def levels(self) -> list[int]:
        return sorted(self.cost)

    def guard_levels(self) -> list[int]:
        return sorted({g for grid in self.guard.values() for row in grid for g in row if g})


@dataclass(frozen=True, slots=True)
class _End:
    crossing: Crossing
    channel: int
    obj: PlacedObject
    tiles: tuple[Spot, ...]


def _interactive(obj: PlacedObject) -> tuple[Spot, ...]:
    cells = [t for t, role in obj.footprint.at(obj.x, obj.y) if role.interactive]
    return tuple(Spot(obj.level, x, y) for x, y in cells or [(obj.x, obj.y)])


def _ring(spot: Spot) -> list[Spot]:
    return [Spot(spot.level, spot.x + dx, spot.y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]


def _pair_underground(ends: list[_End]) -> dict[Spot, tuple[Spot, ...]]:
    upper = sorted((e for e in ends if e.obj.level == 0), key=lambda e: (e.obj.y, e.obj.x))
    lower = [e for e in ends if e.obj.level != 0]
    out: dict[Spot, tuple[Spot, ...]] = {}
    for end in upper:
        if not lower:
            break
        twin = min(lower, key=lambda e: (e.obj.x - end.obj.x) ** 2 + (e.obj.y - end.obj.y) ** 2)
        lower.remove(twin)
        for spot in end.tiles:
            out[spot] = twin.tiles
        for spot in twin.tiles:
            out[spot] = end.tiles
    return out


def _jumps(ends: list[_End]) -> dict[Spot, tuple[Spot, ...]]:
    out = _pair_underground([e for e in ends if e.crossing is Crossing.UNDERGROUND])
    for end in ends:
        if end.crossing is Crossing.TELEPORT:
            twins = [e for e in ends if e.crossing is end.crossing and e.channel == end.channel]
        elif end.crossing is Crossing.ONE_WAY_IN:
            twins = [
                e for e in ends if e.crossing is Crossing.ONE_WAY_OUT and e.channel == end.channel
            ]
        else:
            continue
        landing = tuple(s for e in twins if e.obj is not end.obj for s in e.tiles)
        for spot in end.tiles:
            out[spot] = landing
    return out


def _cost(pace: HeroPace, grid: list[list[Terrain]]) -> list[list[float | None]]:
    return [
        [
            (points / (pace.sea if t.is_water else pace.land))
            if (points := pace.cost.get(t)) is not None
            else None
            for t in row
        ]
        for row in grid
    ]


def _close(
    catalog: Catalog,
    grid: list[list[bool]],
    obj: PlacedObject,
    crossing: tuple[Crossing, int] | None,
) -> None:
    if catalog.is_vanish(obj.kind):
        return
    size = len(grid)
    passed = crossing is not None and crossing[0] in _PASSED
    open_tiles: set[tuple[int, int]] = {(s.x, s.y) for s in _interactive(obj)} if passed else set()
    for (x, y), role in obj.footprint.at(obj.x, obj.y):
        if role.blocks and (x, y) not in open_tiles and 0 <= x < size and 0 <= y < size:
            grid[y][x] = False


def _guard(
    water: dict[int, list[list[bool]]], monsters: list[tuple[Spot, int]]
) -> dict[int, list[list[int]]]:
    guard = {level: [[0] * len(grid) for _ in grid] for level, grid in water.items()}
    for spot, level in monsters:
        grid, ground = guard[spot.level], water[spot.level]
        size = len(grid)
        for s in _ring(spot):
            if 0 <= s.x < size and 0 <= s.y < size and ground[s.y][s.x] == ground[spot.y][spot.x]:
                grid[s.y][s.x] = max(grid[s.y][s.x], level)
    return guard


def _docks(ends: list[_End], water: dict[int, list[list[bool]]]) -> frozenset[Spot]:
    docks: set[Spot] = set()
    for end in ends:
        if end.crossing is Crossing.BOAT:
            docks.update(end.tiles)
        if end.crossing is Crossing.SHIPYARD:
            solid = end.obj.footprint.solid()
            cells = [Spot(end.obj.level, x, y) for (x, y), _ in solid.at(end.obj.x, end.obj.y)]
            grid = water[end.obj.level]
            docks.update(
                s
                for c in cells
                for s in _ring(c)
                if 0 <= s.x < len(grid) and 0 <= s.y < len(grid) and grid[s.y][s.x]
            )
    return frozenset(docks)


def route_map(catalog: Catalog, map_state: MapState) -> RouteMap:
    """The route map of every level of ``map_state``."""
    pace = catalog.pace()
    size = map_state.size
    cost = {level: _cost(pace, grid) for level, grid in map_state.terrain.items()}
    water = {
        level: [[t.is_water for t in row] for row in grid]
        for level, grid in map_state.terrain.items()
    }
    open_ = {level: [[c is not None for c in row] for row in grid] for level, grid in cost.items()}
    ends: list[_End] = []
    monsters: list[tuple[Spot, int]] = []
    for obj in map_state.objs:
        if obj.level not in cost:
            continue
        crossing = catalog.crossing(obj.kind)
        if crossing is not None:
            ends.append(_End(crossing[0], crossing[1], obj, _interactive(obj)))
        level = catalog.creature_level(obj.kind)
        if level is not None:
            monsters.extend((spot, level) for spot in _interactive(obj))
        _close(catalog, open_[obj.level], obj, crossing)
    passed = {s for e in ends if e.crossing in _PASSED for s in e.tiles}
    for level, grid in open_.items():
        for x, y in map_state.gate_blk.get(level, frozenset()):
            if Spot(level, x, y) not in passed:
                grid[y][x] = False
    return RouteMap(
        size=size,
        cost=cost,
        open=open_,
        water=water,
        guard=_guard(water, monsters),
        gates={s: e.channel for e in ends if e.crossing is Crossing.GATE for s in e.tiles},
        tents={s: e.channel for e in ends if e.crossing is Crossing.TENT for s in e.tiles},
        docks=_docks(ends, water),
        jumps=_jumps([e for e in ends if e.crossing in _JUMPS | {Crossing.ONE_WAY_OUT}]),
    )

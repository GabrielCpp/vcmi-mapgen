"""The start room: a player leaving a starting town meets no guard at the gate and is not
walled in. A guard is refused when its zone of control covers a protected entrance tile. A
guard or a solid object is refused when the room a hero can walk from that tile, 8-connected,
outside every zone of control, drops below ROOM tiles and below what it was without it.
Pickups, heroes and towns never count as walls."""

from __future__ import annotations

from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import final

from vcmi_mapgen.core.model import CoverIndex, MapState, PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import PICKUP_PURPOSES, Purpose
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.placement.guards import guard_zoc

ROOM = 12
REACH = ROOM + 1
_NOT_WALLS = frozenset({*PICKUP_PURPOSES, Purpose.HERO, Purpose.TOWN})

type TownKey = tuple[int, int, str, int]


def _key(town: PlacedObject) -> TownKey:
    return (town.x, town.y, town.kind, town.level)


def walls(obj: PlacedObject) -> set[Tile]:
    """The tiles a solid object closes to a hero: its blocking and interactive cells."""
    if obj.purpose in _NOT_WALLS:
        return set()
    return {t for t, role in obj.footprint.at(obj.x, obj.y) if role.blocks or role.interactive}


@dataclass(frozen=True, slots=True)
class Walk:
    """A hero walking the covers of one level, with ``ignore`` lifted off the map."""

    ground: MapState
    level: int
    covers: CoverIndex
    ignore: PlacedObject

    def passable(self, t: Tile) -> bool:
        """A hero may stand on ``t``: on the map, not gate-blocked, not water or rock, and no
        object blocks it or is visited from it, pickups and heroes aside."""
        if not self.ground.in_bounds(*t) or t in self.ground.gate_blk.get(self.level, frozenset()):
            return False
        if self.ground.terrain[self.level][t[1]][t[0]].is_barrier:
            return False
        for c in self.covers.covers_at(t):
            if c.obj is self.ignore:
                continue
            if c.blocking or (
                c.role.interactive
                and c.obj.purpose not in PICKUP_PURPOSES
                and c.obj.purpose != Purpose.HERO
            ):
                return False
        return True

    def threatened(self, t: Tile) -> bool:
        """A guard has ``t`` in its zone of control."""
        return any(
            c.obj is not self.ignore and c.obj.purpose == Purpose.GUARD and c.role.interactive
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            for c in self.covers.covers_at((t[0] + dx, t[1] + dy))
        )

    def room(self, start: Tile, closed: AbstractSet[Tile]) -> int:
        """The tiles a hero walks from ``start``, 8-connected and capped at ROOM, with
        ``closed`` shut."""

        def open_tile(t: Tile) -> bool:
            return t not in closed and not self.threatened(t) and self.passable(t)

        if not open_tile(start):
            return 0
        seen = {start}
        todo = [start]
        while todo and len(seen) < ROOM:
            x, y = todo.pop()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    n = (x + dx, y + dy)
                    if n not in seen and open_tile(n):
                        seen.add(n)
                        todo.append(n)
        return min(len(seen), ROOM)


@final
class StartRoomRule:
    """The start room of every protected player town on one level, as a placement rule. An
    entrance is tested only when the cover index holds its town and the candidate stands
    within REACH tiles of it."""

    def __init__(self, ground: MapState, level: int) -> None:
        self._ground = ground
        self._level = level
        self._fronts: dict[Tile, set[TownKey]] = {}

    def protect(self, town: PlacedObject) -> None:
        approach = FP.footprint_cells(town.footprint, town.x, town.y)[2]
        if approach is not None:
            self._fronts.setdefault(approach, set()).add(_key(town))

    def refuses(self, covers: CoverIndex, obj: PlacedObject) -> list[str]:
        if obj.purpose == Purpose.GUARD:
            cells = set(FP.interactive_cells(obj.footprint, obj.x, obj.y))
            closed = guard_zoc([obj]) if cells else set[Tile]()
        else:
            cells = closed = walls(obj)
        if not cells:
            return []
        walk = Walk(self._ground, self._level, covers, obj)
        problems: list[str] = []
        for ap in self._entrances(covers, cells):
            if ap in closed:
                problems.append(f"{obj.kind} closes the player start at {ap}")
                continue
            room = walk.room(ap, closed)
            if room < ROOM and room < walk.room(ap, frozenset()):
                problems.append(f"{obj.kind} walls in the player start at {ap}")
        return problems

    def _entrances(self, covers: CoverIndex, cells: AbstractSet[Tile]) -> list[Tile]:
        out: list[Tile] = []
        for ap, keys in self._fronts.items():
            if min(max(abs(ap[0] - x), abs(ap[1] - y)) for x, y in cells) > REACH:
                continue
            if any(_key(c.obj) in keys for c in covers.covers_at((ap[0], ap[1] - 1))):
                out.append(ap)
        return out


def start_rules(ground: MapState, level: int) -> tuple[StartRoomRule]:
    """The start room rule of a finished map's player towns on ``level``."""
    rule = StartRoomRule(ground, level)
    for town in ground.player_towns:
        if town.level == level:
            rule.protect(town)
    return (rule,)

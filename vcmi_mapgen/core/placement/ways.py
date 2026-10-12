"""The kept ways: the tiles a player's hero walks from its town out of its home zone, and to
its nearest mine of each basic resource, stay open. A guard is refused when its zone of control
covers one of them, and a solid object when it blocks one or is visited from one. Pickups,
heroes and towns never close a way."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable, Mapping
from collections.abc import Set as AbstractSet
from typing import final

from vcmi_mapgen.core.model import CoverIndex, MapState, PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement.guards import guard_zoc
from vcmi_mapgen.core.placement.start_room import StartRoomRule, walls


@final
class WayRule:
    """The kept ways of one level, as a placement rule."""

    def __init__(self, tiles: Iterable[Tile] = ()) -> None:
        self._tiles: set[Tile] = set(tiles)

    def keep(self, tiles: Iterable[Tile]) -> None:
        """Keep ``tiles`` open from now on."""
        self._tiles.update(tiles)

    def refuses(self, covers: CoverIndex, obj: PlacedObject) -> list[str]:
        del covers
        closed = guard_zoc([obj]) if obj.purpose == Purpose.GUARD else walls(obj)
        hit = sorted(closed & self._tiles)
        return [f"{obj.kind} closes a kept way at {hit[0]}"] if hit else []


def home_ways(
    start: Tile,
    zone_of: Mapping[Tile, int],
    passable: Callable[[Tile], bool],
    threatened: Callable[[Tile], bool],
) -> set[Tile]:
    """Per zone bordering the zone of ``start``, the shortest 8-connected walk from ``start``
    to its first tile, inside the zone of ``start``. A walk stops on a tile a guard
    threatens, as a hero does."""
    home = zone_of.get(start)
    if home is None or not passable(start):
        return set()
    parent: dict[Tile, Tile | None] = {start: None}
    exits: dict[int, tuple[Tile, Tile]] = {}
    todo = deque([start])
    while todo:
        t = todo.popleft()
        if t != start and threatened(t):
            continue
        for n in _around(t):
            if n in parent or not passable(n):
                continue
            zone = zone_of.get(n)
            if zone == home:
                parent[n] = t
                todo.append(n)
            elif zone is not None and zone not in exits:
                exits[zone] = (n, t)
    return {t for out, last in exits.values() for t in (out, *_back(parent, last))}


def _around(t: Tile) -> list[Tile]:
    return [(t[0] + dx, t[1] + dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1)]


def _back(parent: Mapping[Tile, Tile | None], last: Tile) -> list[Tile]:
    path: list[Tile] = []
    at: Tile | None = last
    while at is not None:
        path.append(at)
        at = parent[at]
    return path


def kept_rules(
    ground: MapState, level: int, ways: AbstractSet[Tile]
) -> tuple[StartRoomRule, WayRule]:
    """The rules a later step keeps on ``level`` of a finished map: the start room of each
    player town there and the ``ways`` to the promised mines."""
    rule = StartRoomRule(ground, level)
    for town in ground.player_towns:
        if town.level == level:
            rule.protect(town)
    return rule, WayRule(ways)

"""The ways to the promised mines: the tiles a player's hero walks from its town to its
nearest mine of each basic resource stay open. A guard is refused when its zone of control
covers one of them, and a solid object when it blocks one or is visited from one. Pickups,
heroes and towns never close a way."""

from __future__ import annotations

from collections.abc import Iterable
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
        return [f"{obj.kind} closes the way to a promised mine at {hit[0]}"] if hit else []


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

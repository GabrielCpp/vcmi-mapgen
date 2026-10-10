"""The sealed room: a hero who enters a loot zone walks every open tile of it. A solid object
is refused when its walls split the open tiles of a room it stands in. Pickups, heroes and
towns never count as walls."""

from __future__ import annotations

from collections.abc import Iterable
from collections.abc import Set as AbstractSet
from typing import final

from vcmi_mapgen.core.grid.reach import STEPS8, reach
from vcmi_mapgen.core.model import CoverIndex, PlacedObject, Tile
from vcmi_mapgen.core.placement.start_room import walls


def _open(covers: CoverIndex, t: Tile, ignore: PlacedObject) -> bool:
    return not any(c.obj is not ignore and t in walls(c.obj) for c in covers.covers_at(t))


def _whole(tiles: AbstractSet[Tile]) -> bool:
    return not tiles or len(reach(tiles, [min(tiles)], STEPS8)) == len(tiles)


@final
class RoomRule:
    """The sealed rooms of one level, as a placement rule."""

    def __init__(self, rooms: Iterable[AbstractSet[Tile]] = ()) -> None:
        self._room_of: dict[Tile, frozenset[Tile]] = {}
        for room in rooms:
            frozen = frozenset(room)
            self._room_of.update(dict.fromkeys(frozen, frozen))

    def refuses(self, covers: CoverIndex, obj: PlacedObject) -> list[str]:
        closed = walls(obj)
        rooms = {self._room_of[t] for t in closed if t in self._room_of}
        for room in sorted(rooms, key=min):
            open_ts = {t for t in room if _open(covers, t, obj)}
            for part in _parts(open_ts):
                if not _whole(part - closed):
                    return [f"{obj.kind} splits the sealed room at {min(closed & room)}"]
        return []


def _parts(tiles: AbstractSet[Tile]) -> list[set[Tile]]:
    out: list[set[Tile]] = []
    seen: set[Tile] = set()
    for t in sorted(tiles):
        if t not in seen:
            part = reach(tiles, [t], STEPS8)
            seen |= part
            out.append(part)
    return out

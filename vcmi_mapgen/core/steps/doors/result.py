"""DoorsStep's result."""

from __future__ import annotations

from dataclasses import dataclass

from vcmi_mapgen.core.model import PlacedObject, Tile


@dataclass(frozen=True, slots=True)
class DoorGuard:
    """One guarded door: the map level, the zone pair it crosses, the tile its guard stands
    on, the creature level of the guard and the guard itself."""

    level: int
    zones: tuple[int, int]
    tile: Tile
    guard_level: int
    obj: PlacedObject


@dataclass(frozen=True, slots=True)
class DoorGuards:
    """Every guard DoorsStep posted, a class apart from the prize guards."""

    doors: tuple[DoorGuard, ...] = ()

    def on(self, level: int) -> tuple[DoorGuard, ...]:
        return tuple(d for d in self.doors if d.level == level)

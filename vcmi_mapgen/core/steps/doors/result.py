"""DoorsStep's result."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from vcmi_mapgen.core.model import PlacedObject, Tile


@dataclass(frozen=True, slots=True)
class DoorGuard:
    """One guarded door: the map level, the zone pair it crosses, the tile its guard stands
    on, the creature level of the guard, the guard itself, and the levels the rival cut
    added to the level drawn for it."""

    level: int
    zones: tuple[int, int]
    tile: Tile
    guard_level: int
    obj: PlacedObject
    raised: int = 0


class Shortfall(StrEnum):
    """Why the rival cut left two enemies under a week apart."""

    SEA = "sea"
    PORTAL = "portal"
    OPEN = "no land door"
    CAPPED = "capped door"
    TOP = "top level"


@dataclass(frozen=True, slots=True)
class ShortPair:
    """Two enemy players the rival cut left closer than a week, their hero-days home to
    home, and why."""

    players: tuple[int, int]
    days: int
    reason: Shortfall


@dataclass(frozen=True, slots=True)
class DoorGuards:
    """Every guard DoorsStep posted, a class apart from the prize guards, and the enemy
    pairs the rival cut left under a week apart."""

    doors: tuple[DoorGuard, ...] = ()
    short: tuple[ShortPair, ...] = ()

    def on(self, level: int) -> tuple[DoorGuard, ...]:
        return tuple(d for d in self.doors if d.level == level)

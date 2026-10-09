"""DoorsStep's result."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from vcmi_mapgen.core.model import PlacedObject, Tile
from vcmi_mapgen.core.planning.door_levels import DoorSpread


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
    """Every guard DoorsStep posted, a class apart from the prize guards, the enemy pairs
    the rival cut left under a week apart, and the door spread each level drew, which a
    portal between two territories draws its guard from."""

    doors: tuple[DoorGuard, ...] = ()
    short: tuple[ShortPair, ...] = ()
    spreads: Mapping[int, DoorSpread] = field(default_factory=dict[int, DoorSpread])

    def on(self, level: int) -> tuple[DoorGuard, ...]:
        return tuple(d for d in self.doors if d.level == level)

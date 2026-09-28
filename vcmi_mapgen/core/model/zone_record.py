from __future__ import annotations

from dataclasses import dataclass, field

from vcmi_mapgen.core.model.objects import Tile


@dataclass(slots=True)
class ZoneRecord:
    zid: int
    terrain: str
    ts: frozenset[Tile]
    open_set: set[Tile]
    passable: set[Tile]
    reach: set[Tile] = field(default_factory=set)
    used: set[Tile] = field(default_factory=set)
    loot_zone: bool = False

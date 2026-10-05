"""GatedStep's result."""

from __future__ import annotations

from dataclasses import dataclass, field

from vcmi_mapgen.core.model import Tile


@dataclass(frozen=True, slots=True)
class LootAccess:
    """How a loot zone is entered: the inside tile next to the access object, the access
    object's footprint and its visit tiles."""

    entry: Tile
    footprint: frozenset[Tile]
    interactive: frozenset[Tile]


@dataclass
class GatedResult:
    """The access of every loot zone, per level and zone id."""

    access: dict[int, dict[int, LootAccess]] = field(default_factory=dict)

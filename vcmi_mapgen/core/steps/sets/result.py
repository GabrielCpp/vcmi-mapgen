"""SetsStep's result."""

from __future__ import annotations

from dataclasses import dataclass, field

from vcmi_mapgen.core.model import PlacedObject


@dataclass(frozen=True, slots=True)
class PlacedSet:
    """One complete set on the map: its name, the pickup of each part and the effort band of
    the slot each part stands on."""

    name: str
    parts: tuple[PlacedObject, ...]
    bands: tuple[int, ...] = ()


@dataclass
class SetsResult:
    """The sets the map carries, and how many held slots took a fallback prize or stayed
    empty."""

    sets: list[PlacedSet] = field(default_factory=list)
    filled: int = 0
    empty: int = 0

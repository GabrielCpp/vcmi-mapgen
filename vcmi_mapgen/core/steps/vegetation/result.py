"""VegetationStep's result."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from vcmi_mapgen.core.model import Tile


@dataclass(frozen=True, slots=True)
class VegetatedZone:
    """One zone after vegetation and the border seal: the tiles left open for objects and the
    tiles a hero can walk. A zone whose terrain grows no vegetation keeps both empty."""

    open_set: frozenset[Tile] = frozenset()
    passable: frozenset[Tile] = frozenset()


@dataclass(frozen=True, slots=True)
class VegetationResult:
    """Diagnostic log lines for the CLI to print, and each zone after vegetation by level
    and zid."""

    log: tuple[str, ...] = ()
    zones: Mapping[int, Mapping[int, VegetatedZone]] = field(
        default_factory=dict[int, Mapping[int, VegetatedZone]]
    )


@dataclass(frozen=True, slots=True)
class LootZones:
    """The zones a gate or a monolith pair will seal, by level. No door guard stands at
    their door and no gameplay object stands in them."""

    levels: Mapping[int, frozenset[int]] = field(default_factory=dict[int, frozenset[int]])

    def on(self, level: int) -> frozenset[int]:
        return self.levels.get(level, frozenset())

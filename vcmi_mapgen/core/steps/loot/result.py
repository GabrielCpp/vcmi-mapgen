"""LootStep's result."""

from __future__ import annotations

from dataclasses import dataclass, field

from vcmi_mapgen.core.grid.pockets import Pockets


@dataclass
class LootResult:
    """Pocket geometry for PocketOverlay (level -> {tile: normalized depth 0..1}). Disposable
    analysis, not a map fact, so it is not a MapState field."""

    pockets: Pockets = field(default_factory=dict)

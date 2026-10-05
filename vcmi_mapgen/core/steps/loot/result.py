"""LootStep's result."""

from __future__ import annotations

from dataclasses import dataclass, field

from vcmi_mapgen.core.grid.pockets import Pockets
from vcmi_mapgen.core.placement.prizes import HeldPrize


@dataclass
class LootResult:
    """Pocket geometry for PocketOverlay (level -> {tile: normalized depth 0..1}). Disposable
    analysis, not a map fact, so it is not a MapState field. ``held`` lists the prize slots
    the pocket guards keep open for the sets step."""

    pockets: Pockets = field(default_factory=dict)
    held: tuple[HeldPrize, ...] = ()

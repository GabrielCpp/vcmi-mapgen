"""What CompensationStep publishes: the value each player claimed first before the prizes, the
prizes it stood, and the players still behind the bar after them."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from vcmi_mapgen.core.model.artifact import ArtifactTier
from vcmi_mapgen.core.reading.routes import Spot


@dataclass(frozen=True, slots=True)
class Prize:
    """One guarded artifact: the player it serves, its tier, its guard level, where it stands
    and the days that player takes to win it."""

    player: int
    tier: ArtifactTier
    guard: int
    spot: Spot
    days: int


@dataclass(frozen=True, slots=True)
class CompensationResult:
    """Per horizon, the value each player claimed first before the prizes; the prizes; and
    the players the prizes leave below the bar, with the gold each still lacks."""

    claimed: Mapping[int, tuple[int, ...]]
    prizes: tuple[Prize, ...]
    behind: Mapping[int, int]

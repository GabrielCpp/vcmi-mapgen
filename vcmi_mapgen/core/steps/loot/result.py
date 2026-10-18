"""LootStep's result."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from vcmi_mapgen.core.grid.pockets import Pockets
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.placement.prizes import HeldPrize


@dataclass(frozen=True, slots=True)
class QuestDecision:
    """One seer-hut quest: the hut and the zone it stands in, the artifact it asks for, where
    that artifact lies and in which zone."""

    level: int
    hut: Tile
    hut_zone: int | None
    artifact_tile: Tile
    artifact_zone: int | None
    artifact: str


class PocketOutcome(StrEnum):
    GUARDED = "guarded"
    UNGUARDED = "unguarded"
    NO_ZONE = "no_zone"
    NO_GUARD_SPOT = "no_guard_spot"
    NO_CACHE_SPOT = "no_cache_spot"
    GUARD_REFUSED = "guard_refused"
    NO_FREE_TILE = "no_free_tile"
    EMPTY = "empty"


@dataclass(frozen=True, slots=True)
class PocketDecision:
    """What the loot step did with one pocket: its zone, whether the pocket plan covers it
    and its kind there, the tiles and mouth of the candidate used (else the largest), the
    outcome, the guard's tile and level, the ward's tile and tier and whether it is held for
    the sets step, and each new object's anchor and purpose."""

    level: int
    zone: int | None
    planned: bool
    kind: str | None
    tiles: tuple[Tile, ...]
    mouth: tuple[Tile, ...]
    outcome: PocketOutcome
    guard: tuple[Tile, int] | None = None
    ward: Tile | None = None
    ward_tier: str | None = None
    ward_held: bool = False
    placed: tuple[tuple[Tile, str], ...] = ()


@dataclass
class LootResult:
    """Pocket geometry for PocketOverlay (level -> {tile: normalized depth 0..1}). Disposable
    analysis, not a map fact, so it is not a MapState field. ``held`` lists the prize slots
    the pocket guards keep open for the sets step. ``quests`` and ``decisions`` record each
    seer-hut quest and each pocket the step examined."""

    pockets: Pockets = field(default_factory=dict)
    held: tuple[HeldPrize, ...] = ()
    quests: tuple[QuestDecision, ...] = ()
    decisions: tuple[PocketDecision, ...] = ()

"""GameplayStep's results."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from vcmi_mapgen.core.model import PlacedObject, Tile
from vcmi_mapgen.core.placement.site import PlacedZone
from vcmi_mapgen.core.planning.zone_plan import Landings


@dataclass
class GateResult:
    """The gate pairs with their guards and the cells they block per level. PortalStep reads
    it with ``ctx.get(GateResult, GateResult())``: a map without subterrain has none."""

    gate_objs: list[PlacedObject] = field(default_factory=list)
    gate_blk: dict[int, frozenset[Tile]] = field(default_factory=dict)


@dataclass
class TownsIndex:
    """Which zones host a player town: PortalStep's, LootStep's and the CLI's
    input. A run stopped before GameplayStep reads the empty default."""

    player_zids: list[tuple[int, int]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Shortfall:
    """Per family, the objects the plan asked for and the objects that stood."""

    wanted: Mapping[str, int]
    placed: Mapping[str, int]

    def lines(self) -> list[str]:
        return [
            f"{f}: {self.placed.get(f, 0)}/{n}"
            for f, n in sorted(self.wanted.items())
            if self.placed.get(f, 0) < n
        ]


RANKED_KEEP = 10
GROUPS_KEEP = 40


@dataclass(frozen=True, slots=True)
class RankedTile:
    """One site tile a slot ranked, with its zone and the values of the sort columns."""

    level: int
    x: int
    y: int
    zid: int
    values: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class GroupStep:
    """One group a slot visited: its head tile, zone and size, the values of the sort columns
    at the head, and what came of it: ``tier_tried``, ``zone_full``, ``no_object``,
    ``no_room`` or ``stood``."""

    index: int
    level: int
    x: int
    y: int
    zid: int
    size: int
    values: tuple[int, ...]
    outcome: str


@dataclass(frozen=True, slots=True)
class Stood:
    """Where a slot's object stood and how: the family it stood as, the guard it stood
    behind, the footing pass, whether the smaller-object fallback stood it, the index of the
    group it stood in, whether the strict turn pass took it and whether it stood past its
    zone cap. ``centre`` is the centre whose window produced the anchor, ``rank`` its place
    among the group's tiles in sort order (-1 when absent) and ``tried_at`` its place among the
    centres in the order the site tried them."""

    level: int
    x: int
    y: int
    family: str
    guard: int
    footing: str
    smaller: bool
    group: int
    strict: bool
    lax: bool
    centre: tuple[int, int]
    rank: int
    tried_at: int


@dataclass(frozen=True, slots=True)
class SlotRanking:
    """One slot of the map-wide pass: its family, player, band, target and drawn guard, the
    names of the sort columns in priority order, the first tiles of the group it stood in (of
    the first group when nothing stood), the groups it walked with their outcomes (at most
    GROUPS_KEEP, the stood one always kept), how many groups the pass visited and where its
    object stood, None when nothing stood."""

    order: int
    family: str
    player: int | None
    band: int | None
    target: int | None
    guard: int
    keys: tuple[str, ...]
    ranked: tuple[RankedTile, ...]
    groups: tuple[GroupStep, ...]
    groups_seen: int
    stood: Stood | None


@dataclass(frozen=True, slots=True)
class GameplayResult:
    """Each zone after placement by level and zid, each level's seaport landings recomputed
    from the placed shipyards, the first town each zone received, diagnostic log lines
    for the CLI to print, and what the map-wide pass asked per family against what stood."""

    zones: Mapping[int, Mapping[int, PlacedZone]]
    landings: Mapping[int, Landings]
    town_of_zone: Mapping[int, Mapping[int, PlacedObject]]
    log: tuple[str, ...] = ()
    shortfall: Shortfall = Shortfall({}, {})
    ranking: tuple[SlotRanking, ...] = ()


@dataclass(frozen=True, slots=True)
class PromisedWays:
    """Per level, the tiles each player's hero walks from its town to its nearest mine of each
    basic resource, and the land tiles of its way by sea to a rival town. Every later
    placement step keeps them open with ``kept_rules``. A run stopped before GameplayStep
    reads the empty default."""

    tiles: Mapping[int, frozenset[Tile]] = field(default_factory=dict[int, frozenset[Tile]])

    def on(self, level: int) -> frozenset[Tile]:
        """The kept tiles of ``level``."""
        return self.tiles.get(level, frozenset())

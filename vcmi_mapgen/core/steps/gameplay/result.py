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
class GameplayResult:
    """Each zone after placement by level and zid, each level's seaport landings recomputed
    from the placed shipyards, and the first town each zone received."""

    zones: Mapping[int, Mapping[int, PlacedZone]]
    landings: Mapping[int, Landings]
    town_of_zone: Mapping[int, Mapping[int, PlacedObject]]


@dataclass(frozen=True, slots=True)
class PromisedWays:
    """Per level, the tiles each player's hero walks from its town to its nearest mine of each
    basic resource. Every later placement step keeps them open with ``kept_rules``. A run
    stopped before GameplayStep reads the empty default."""

    tiles: Mapping[int, frozenset[Tile]] = field(default_factory=dict[int, frozenset[Tile]])

    def on(self, level: int) -> frozenset[Tile]:
        """The kept tiles of ``level``."""
        return self.tiles.get(level, frozenset())

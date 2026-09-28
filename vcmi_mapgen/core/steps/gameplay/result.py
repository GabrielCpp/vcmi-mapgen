"""GameplayStep's results."""

from __future__ import annotations

from dataclasses import dataclass, field

from vcmi_mapgen.core.model import PlacedObject, Tile


@dataclass
class GateResult:
    """The gate pairs with their guards and the cells they block per level. PortalStep reads
    it with ``ctx.get(GateResult, GateResult())``: a map without subterrain has none."""

    gate_objs: list[PlacedObject] = field(default_factory=list)
    gate_blk: dict[int, frozenset[Tile]] = field(default_factory=dict)


@dataclass
class TownsIndex:
    """Which zones host a player town: PortalStep's, LootStep's, BorderStep's and the CLI's
    input. A run stopped before GameplayStep reads the empty default."""

    player_zids: list[tuple[int, int]] = field(default_factory=list)

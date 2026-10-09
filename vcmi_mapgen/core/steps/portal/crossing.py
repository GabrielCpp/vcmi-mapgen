"""The territory rules of a portal pair: the side each end stands on, the sides a pair may
join, and the level of the guard it takes."""

from __future__ import annotations

import random
from dataclasses import dataclass

from vcmi_mapgen.core.planning.door_levels import DoorSpread, spread_level
from vcmi_mapgen.core.steps.terrain_gen.result import TerritoryPlan


@dataclass(frozen=True, slots=True)
class Side:
    """The planned territory a portal end stands in and the player who owns it. Either is
    None when the end's zone lies in no planned territory or the territory is neutral."""

    territory: int | None = None
    owner: int | None = None


def side_of(plan: TerritoryPlan, zid: int) -> Side:
    """The side of zone ``zid`` in ``plan``."""
    territory = plan.zones.get(zid)
    if territory is None:
        return Side()
    owner = plan.owners[territory] if territory < len(plan.owners) else None
    return Side(territory, owner)


def may_join(a: Side, b: Side) -> bool:
    """Whether a portal pair may join ``a`` to ``b``: never two player territories."""
    return a.owner is None or b.owner is None or a.territory == b.territory


def pair_guard_level(
    spread: DoorSpread, ends: tuple[Side, Side], prize_level: int, rng: random.Random
) -> int:
    """The creature level of the guard beside a portal pair. A pair inside one territory
    keeps ``prize_level``. A pair between two territories draws from the door spread, from
    the doors out of a player territory when either end stands in one."""
    a, b = ends
    if a.territory == b.territory:
        return prize_level
    return spread_level(spread, a.owner is not None or b.owner is not None, rng)

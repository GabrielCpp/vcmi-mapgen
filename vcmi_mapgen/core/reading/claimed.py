"""The value each player claims first: per player, the gold-equivalent value of the rewards it
reaches within a horizon of hero-days with no other player sooner, against the best player's.

An object counts at its effort with its own guard, since the claimer must beat it. Two
players reaching an object on the same day both claim it."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.reading.effort import EffortMap, effort_map
from vcmi_mapgen.core.reading.ground import TownKey
from vcmi_mapgen.core.reading.homes import town_spots
from vcmi_mapgen.core.reading.promise import doors
from vcmi_mapgen.core.reading.routes import RouteMap, route_map
from vcmi_mapgen.core.reading.value import ValueTable, value_of

CLAIM_DAYS = (5, 10, 20, 40)


@dataclass(frozen=True, slots=True)
class Claim:
    """One reward: its value and, per player, the days to visit it, None when that player
    never reaches it."""

    value: int
    days: tuple[int | None, ...]


def claimed(claims: Sequence[Claim], within: int) -> tuple[int, ...]:
    """Per player, the value of the rewards it reaches within ``within`` days with no other
    player sooner."""
    players = max((len(c.days) for c in claims), default=0)
    out = [0] * players
    for c in claims:
        reached = [d for d in c.days if d is not None]
        if not reached:
            continue
        first = min(reached)
        if first > within:
            continue
        for i, d in enumerate(c.days):
            if d == first:
                out[i] += c.value
    return tuple(out)


def worst_share(claims: Sequence[Claim], within: int) -> float | None:
    """The worst player's claimed value over the best player's, None when nobody claims
    anything within ``within`` days."""
    per = claimed(claims, within)
    if not per or max(per) == 0:
        return None
    return min(per) / max(per)


def owner_maps(
    catalog: Catalog,
    state: MapState,
    owners: Mapping[TownKey, int],
    toll: Sequence[int],
    route: RouteMap | None = None,
) -> list[EffortMap]:
    """One effort map per player that owns a town, in player order, each from the visit tiles
    of every town it owns, over ``route`` or the route map of ``state``."""
    route = route if route is not None else route_map(catalog, state)
    homes = {
        p: [s for o in state.objs if owners.get((o.x, o.y, o.level)) == p for s in town_spots(o)]
        for p in sorted(set(owners.values()))
    }
    return [effort_map(route, spots, toll) for spots in homes.values() if spots]


def claims_of(catalog: Catalog, state: MapState, maps: Sequence[EffortMap]) -> list[Claim]:
    """Each reward on ``state`` some player reaches, with its value and its days per player of
    ``maps``, its own guard counted."""
    table = ValueTable.of(catalog)
    out: list[Claim] = []
    for o in state.objs:
        value = value_of(catalog, table, o)
        if value <= 0:
            continue
        days: list[int | None] = []
        for em in maps:
            found = [e.total for d in doors(o) if (e := em.visit(d)) is not None]
            days.append(min(found) if found else None)
        if any(d is not None for d in days):
            out.append(Claim(value, tuple(days)))
    return out

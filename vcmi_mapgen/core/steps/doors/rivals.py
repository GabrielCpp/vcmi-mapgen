"""The rival cut: enemies start at least ``RIVAL_DAYS`` hero-days apart, home to home. While
an enemy pair is closer, the strongest door guard on their cheapest route takes one level
more, because a hero pays only the strongest guard on a route. A route that sails or steps
through a portal may stay short, and so may a route through a door already at its cap or at
the top level."""

from __future__ import annotations

import itertools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.planning.door_levels import TOP_LEVEL
from vcmi_mapgen.core.reading.effort import effort_map
from vcmi_mapgen.core.reading.routes import RouteMap, Spot, with_guards
from vcmi_mapgen.core.steps.doors.result import Shortfall, ShortPair

RIVAL_DAYS = 7


@dataclass(frozen=True, slots=True)
class RivalDoor:
    """One door guard the cut may raise: the spot it stands on, the level drawn for it and
    the strongest level it may take."""

    spot: Spot
    level: int
    cap: int = TOP_LEVEL


@dataclass(frozen=True, slots=True)
class Leg:
    """The cheapest route between two homes: its hero-days, the doors whose guard watches
    it, and the sea or portal crossing it takes, None when it stays on land."""

    total: int
    doors: tuple[int, ...]
    crossing: Shortfall | None


@dataclass(frozen=True, slots=True)
class RivalCut:
    """The level of each door after the cut, in the order of the doors given, and the
    enemy pairs it left under ``RIVAL_DAYS``."""

    levels: tuple[int, ...]
    short: tuple[ShortPair, ...]


def enemy_pairs(players: int, teams: Sequence[int] = ()) -> list[tuple[int, int]]:
    """Every pair of players on different teams. Without ``teams`` every other player is
    an enemy."""
    team = list(teams) or list(range(players))
    return [(a, b) for a, b in itertools.combinations(range(players), 2) if team[a] != team[b]]


def _watches(route: RouteMap, door: Spot, tile: Spot) -> bool:
    water = route.water[door.level]
    return (
        tile.level == door.level
        and max(abs(tile.x - door.x), abs(tile.y - door.y)) <= 1
        and water[tile.y][tile.x] == water[door.y][door.x]
    )


def _crossing(route: RouteMap, tiles: Sequence[Spot]) -> Shortfall | None:
    if any(route.water[t.level][t.y][t.x] for t in tiles):
        return Shortfall.SEA
    jumps = (
        p.level != q.level or max(abs(p.x - q.x), abs(p.y - q.y)) > 1
        for p, q in itertools.pairwise(tiles)
    )
    return Shortfall.PORTAL if any(jumps) else None


def rival_leg(
    route: RouteMap,
    toll: Sequence[int],
    doors: Sequence[tuple[Spot, int]],
    ends: tuple[Spot, Spot],
) -> Leg | None:
    """The cheapest route between ``ends`` once each door guard of ``doors``, a spot and a
    level, stands on ``route``. None when no route joins them."""
    guarded = with_guards(route, doors)
    em = effort_map(guarded, [ends[0]], toll)
    effort = em.at(ends[1])
    if effort is None:
        return None
    tiles = em.path(ends[1])
    met = tuple(
        i for i, (spot, _) in enumerate(doors) if any(_watches(route, spot, t) for t in tiles)
    )
    return Leg(effort.total, met, _crossing(route, tiles))


def _raise(leg: Leg, doors: Sequence[RivalDoor], levels: list[int]) -> Shortfall | None:
    if leg.crossing is not None:
        return leg.crossing

    def rank(i: int) -> tuple[int, bool, int]:
        return levels[i], levels[i] < min(doors[i].cap, TOP_LEVEL), -i

    door = max(leg.doors, key=rank, default=None)
    if door is None:
        return Shortfall.OPEN
    if levels[door] >= TOP_LEVEL:
        return Shortfall.TOP
    if levels[door] >= doors[door].cap:
        return Shortfall.CAPPED
    levels[door] += 1
    return None


def cut_rivals(
    route: RouteMap,
    toll: Sequence[int],
    doors: Sequence[RivalDoor],
    homes: Mapping[int, Spot],
    pairs: Sequence[tuple[int, int]],
) -> RivalCut:
    """Raise door guards until every enemy pair of ``pairs`` with both ``homes`` known
    stands ``RIVAL_DAYS`` apart on ``route``, or record why the pair stays short."""
    levels = [d.level for d in doors]
    short: list[ShortPair] = []
    for a, b in pairs:
        if a not in homes or b not in homes:
            continue
        while True:
            placed = [(d.spot, lv) for d, lv in zip(doors, levels, strict=True)]
            leg = rival_leg(route, toll, placed, (homes[a], homes[b]))
            if leg is None or leg.total >= RIVAL_DAYS:
                break
            reason = _raise(leg, doors, levels)
            if reason is not None:
                short.append(ShortPair((a, b), leg.total, reason))
                break
    return RivalCut(tuple(levels), tuple(short))

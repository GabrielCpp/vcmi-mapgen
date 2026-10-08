"""The door guard decisions: which doors stay open, how strong a guard each door may take
on a player's way to its mines, the creature level of each guard and the door tile it
stands on."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass

from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.priors.territories import TerritoryStats
from vcmi_mapgen.core.reading.places import PlaceRole
from vcmi_mapgen.core.steps.terrain_gen.result import PlannedDoor, PlannedPlace, TerritoryPlan

DEFAULT_DOOR_LEVEL = 3
TOP_LEVEL = 7
PLAYER_DOOR_TRAVEL = 4
HOME_ROOM = 600


def _strongest(toll: Sequence[int], days: float) -> int:
    fits = [lv for lv in range(1, min(len(toll), TOP_LEVEL + 1)) if toll[lv] <= days]
    return max(fits, default=1)


def territory_areas(label: Sequence[Sequence[int]], zones: Mapping[int, int]) -> Counter[int]:
    """The planned tiles of each territory, from the label grid read ``[y][x]``."""
    return Counter(zones[z] for row in label for z in row if z in zones)


def home_reach(
    home: int, doors: Sequence[PlannedDoor], areas: Mapping[int, int]
) -> tuple[int, tuple[int, ...]]:
    """How many doors deep a player in territory ``home`` goes before the territories it
    reaches hold ``HOME_ROOM`` tiles, and the index of every door it crosses on the way."""
    seen = {home}
    area = areas.get(home, 0)
    depth = 0
    crossed: list[int] = []
    while area < HOME_ROOM:
        step = [
            (i, b)
            for i, d in enumerate(doors)
            for a, b in (d.territories, d.territories[::-1])
            if a in seen and b not in seen
        ]
        if not step:
            break
        depth += 1
        crossed += sorted({i for i, _ in step})
        fresh = {b for _, b in step}
        seen |= fresh
        area += sum(areas.get(t, 0) for t in fresh)
    return depth, tuple(crossed)


def door_caps(
    plan: TerritoryPlan, areas: Mapping[int, int], toll: Sequence[int], days: int
) -> dict[int, int]:
    """The strongest guard level of each door a player crosses to reach ``HOME_ROOM``
    tiles, by door index. The tolls of those doors together leave ``PLAYER_DOOR_TRAVEL`` of
    the ``days`` within which a player reaches its mines."""
    caps: dict[int, int] = {}
    homes = sorted(t for t, owner in enumerate(plan.owners) if owner is not None)
    for home in homes:
        depth, crossed = home_reach(home, plan.doors, areas)
        cap = _strongest(toll, (days - PLAYER_DOOR_TRAVEL) / max(depth, 1))
        for i in crossed:
            caps[i] = min(caps.get(i, TOP_LEVEL), cap)
    return caps


@dataclass(frozen=True, slots=True)
class DoorSpread:
    """The door levels one corpus map gives a generated level: those of its doors out of a
    player territory and those of its doors between neutral ones."""

    player: tuple[int, ...] = ()
    neutral: tuple[int, ...] = ()

    @classmethod
    def draw(cls, stats: TerritoryStats, rng: random.Random) -> DoorSpread:
        """The player doors of one corpus map and the neutral doors of one, each drawn
        among the maps that have such doors."""
        player = rng.choice(stats.player_doors_by_map) if stats.player_doors_by_map else ()
        neutral = rng.choice(stats.neutral_doors_by_map) if stats.neutral_doors_by_map else ()
        return cls(player, neutral)


def door_level(
    spread: DoorSpread, door: PlannedDoor, rng: random.Random, cap: int = TOP_LEVEL
) -> int:
    """The creature level of a door's guard up to ``cap``, drawn from the map's doors out
    of a player territory when one side is a player's, from its doors between neutral ones
    otherwise, and ``DEFAULT_DOOR_LEVEL`` within the cap when that spread holds no level it
    allows."""
    levels = spread.player if door.player_side() is not None else spread.neutral
    levels = [n for n in levels if 1 <= n <= cap]
    return rng.choice(levels) if levels else min(DEFAULT_DOOR_LEVEL, cap)


def open_zones(
    places: Mapping[int, PlannedPlace],
    loot: AbstractSet[int],
    doors: Sequence[PlannedDoor],
) -> frozenset[int]:
    """The zones whose doors stay unguarded: the loot zones a seal will close and the
    planned treasure places with a single door. A treasure place with two doors or more is
    a way through, so its doors take guards."""
    count = Counter(z for d in doors for z in d.zones)
    return frozenset(loot) | {
        z for z, p in places.items() if p.role == PlaceRole.TREASURE and count[z] <= 1
    }


def door_tile(door: PlannedDoor, fits: Callable[[Tile], bool]) -> Tile | None:
    """The first tile of the door a guard ``fits`` on, None when neither takes one."""
    return next((t for t in door.tiles if fits(t)), None)

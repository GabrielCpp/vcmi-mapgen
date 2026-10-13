"""The door guard decisions: which doors stay open, the creature level of each guard and
the door tile it stands on."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from collections.abc import Set as AbstractSet

from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.planning.door_levels import TOP_LEVEL, DoorSpread, spread_level
from vcmi_mapgen.core.reading.places import PlaceRole
from vcmi_mapgen.core.steps.terrain_gen.result import PlannedDoor, PlannedPlace, TerritoryPlan

PLAYER_DOOR_TRAVEL = 4


def territory_areas(label: Sequence[Sequence[int]], zones: Mapping[int, int]) -> Counter[int]:
    """The planned tiles of each territory, from the label grid read ``[y][x]``."""
    return Counter(zones[z] for row in label for z in row if z in zones)


def home_room(plan: TerritoryPlan, areas: Mapping[int, int]) -> float:
    """The tiles a home holds before a guard may stand on its way out: the mean planned
    tiles of the homes on the level, so a home smaller than its rivals' reaches as much
    land as them before it meets a guard."""
    homes = [areas.get(t, 0) for t, owner in enumerate(plan.owners) if owner is not None]
    return sum(homes) / max(1, len(homes))


def home_reach(
    home: int, doors: Sequence[PlannedDoor], areas: Mapping[int, int], room: float
) -> tuple[int, tuple[int, ...]]:
    """How many doors deep a player in territory ``home`` goes before the territories it
    reaches hold ``room`` tiles, and the index of every door it crosses on the way. It
    stops short of a layer of doors that would overshoot the room by as much as the land
    falls short of it."""
    seen = {home}
    area = areas.get(home, 0)
    depth = 0
    crossed: list[int] = []
    while area < room:
        step = [
            (i, b)
            for i, d in enumerate(doors)
            for a, b in (d.territories, d.territories[::-1])
            if a in seen and b not in seen
        ]
        fresh = {b for _, b in step}
        gain = sum(areas.get(t, 0) for t in fresh)
        if not step or area + gain - room >= room - area:
            break
        depth += 1
        crossed += sorted({i for i, _ in step})
        seen |= fresh
        area += gain
    return depth, tuple(crossed)


def home_doors(plan: TerritoryPlan, areas: Mapping[int, int]) -> frozenset[int]:
    """The index of each door a player crosses before its land holds its ``home_room``.
    No guard stands on a player's way out of a cramped home, unless the open door would
    join the land of two players."""
    group = list(range(len(plan.owners)))
    owners = [{o} - {None} for o in plan.owners]

    def root(t: int) -> int:
        while group[t] != t:
            t = group[t]
        return t

    room = home_room(plan, areas)
    opened: set[int] = set()
    homes = sorted(t for t, owner in enumerate(plan.owners) if owner is not None)
    for i in sorted({i for home in homes for i in home_reach(home, plan.doors, areas, room)[1]}):
        a, b = (root(t) for t in plan.doors[i].territories)
        if a != b and owners[a] and owners[b]:
            continue
        group[b] = a
        owners[a] |= owners[b]
        opened.add(i)
    return frozenset(opened)


def home_land(plan: TerritoryPlan, opened: AbstractSet[int]) -> frozenset[int]:
    """The territories a player walks into from its home through the ``opened`` doors, the
    homes among them."""
    land = {t for t, owner in enumerate(plan.owners) if owner is not None}
    grown = True
    while grown:
        fresh = {
            b
            for i in opened
            for a, b in (plan.doors[i].territories, plan.doors[i].territories[::-1])
            if a in land and b not in land
        }
        land |= fresh
        grown = bool(fresh)
    return frozenset(land)


def player_door_cap(
    door: PlannedDoor, land: AbstractSet[int], toll: Sequence[int], days: int
) -> int:
    """The strongest guard level a door out of a player's home ``land`` takes: its toll
    leaves ``PLAYER_DOOR_TRAVEL`` of the ``days`` within which a player reaches its mines.
    A door between two territories off that land takes any level."""
    if not any(t in land for t in door.territories):
        return TOP_LEVEL
    fits = [
        lv
        for lv in range(1, min(len(toll), TOP_LEVEL + 1))
        if toll[lv] <= days - PLAYER_DOOR_TRAVEL
    ]
    return max(fits, default=1)


def door_level(
    spread: DoorSpread, door: PlannedDoor, rng: random.Random, cap: int = TOP_LEVEL
) -> int:
    """The creature level of a door's guard up to ``cap``, drawn from the map's doors out
    of a player territory when one side is a player's, from its doors between neutral ones
    otherwise, and ``DEFAULT_DOOR_LEVEL`` within the cap when that spread holds no level it
    allows."""
    return spread_level(spread, door.player_side() is not None, rng, cap)


def open_zones(
    places: Mapping[int, PlannedPlace],
    loot: AbstractSet[int],
    plan: TerritoryPlan,
) -> frozenset[int]:
    """The zones whose doors stay unguarded: the loot zones a seal will close and the
    planned treasure places that are a dead end, a territory of their own with a single
    door. A treasure place with two doors or more, or one that shares its territory, is a
    way through, so its doors take guards."""
    count = Counter(z for d in plan.doors for z in d.zones)
    size = Counter(plan.zones.values())
    return frozenset(loot) | {
        z
        for z, p in places.items()
        if p.role == PlaceRole.TREASURE
        and count[z] <= 1
        and z in plan.zones
        and size[plan.zones[z]] == 1
    }


def door_tile(door: PlannedDoor, fits: Callable[[Tile], bool]) -> Tile | None:
    """The first tile of the door a guard ``fits`` on, None when neither takes one."""
    return next((t for t in door.tiles if fits(t)), None)

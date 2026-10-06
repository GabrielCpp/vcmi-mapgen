"""Family efforts on a small literal grid: a mine's own guard stays out of its effort, and
the player town stays out of the reading. Reach counts the own guard of every object but a
mine."""

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Footprint, MapState, PlacedObject, Role
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.reading.families import (
    FAR_DAYS,
    family_days,
    guard_levels,
    histogram,
    reach_guard,
)
from vcmi_mapgen.core.reading.promise import doors
from vcmi_mapgen.core.reading.routes import Spot

SIZE = 40
TOLL = (0, 3, 5, 8, 12, 18, 28, 45)


def _obj(t: tuple[int, int], purpose: str, kind: str, role: Role) -> PlacedObject:
    return PlacedObject(t[0], t[1], 0, purpose, kind, Footprint.one(role))


def test_a_mine_is_priced_without_its_own_guard(catalog: Catalog) -> None:
    grid = [[Terrain.GRASS] * SIZE for _ in range(SIZE)]
    town = _obj((0, 0), Purpose.TOWN, "randomTown", Role.VISIT)
    sawmill = catalog.mines_by_resource("grass")["sawmill"][0]
    mine = PlacedObject(30, 3, 0, Purpose.MINE, sawmill.kind, sawmill.footprint)
    door = doors(mine)[0]
    guard = _obj((door.x - 1, door.y + 1), Purpose.GUARD, catalog.guard(5).kind, Role.VISIT)
    state = MapState(size=SIZE, terrain={0: grid}, objs=[town, mine, guard])
    found = family_days(catalog, state, [Spot(0, 0, 0)], {(0, 0, 0)}, TOLL)
    assert found == [("MINE:sawmill", 2)]


def test_the_histogram_holds_far_efforts_in_its_last_count() -> None:
    counts = histogram([0, 3, 3, FAR_DAYS + 9])
    assert (counts[0], counts[3], counts[FAR_DAYS]) == (1, 2, 1)


def test_reach_counts_the_own_guard_of_all_but_a_mine(catalog: Catalog) -> None:
    sawmill = catalog.mines_by_resource("grass")["sawmill"][0]
    mine = PlacedObject(30, 3, 0, Purpose.MINE, sawmill.kind, sawmill.footprint)
    shrine = _obj((10, 10), Purpose.SPELL_SKILL, "shrineOfMagicIncantation", Role.VISIT)
    near = [doors(mine)[0], doors(shrine)[0]]
    objs = [_obj((d.x, d.y + 1), Purpose.GUARD, catalog.guard(4).kind, Role.VISIT) for d in near]
    guards = guard_levels(catalog, objs)
    assert (reach_guard(catalog, guards, mine), reach_guard(catalog, guards, shrine)) == (0, 4)

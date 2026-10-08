from vcmi_mapgen.core.reading.routes import RouteMap, Spot, with_guards
from vcmi_mapgen.core.steps.doors.result import Shortfall, ShortPair
from vcmi_mapgen.core.steps.doors.rivals import RivalDoor, cut_rivals, enemy_pairs

STEP = 100 / 1500
NO_DOCKS: frozenset[Spot] = frozenset()
TOLL = (0, 1, 2, 3, 4, 5, 6, 7)
FLAT_TOLL = (0, 1, 1, 1, 1, 1, 1, 1)


def grid_route(rows: list[str], docks: frozenset[Spot] = NO_DOCKS) -> RouteMap:
    size = max(len(rows), len(rows[0]))
    rows = [r.ljust(size, "#") for r in rows] + ["#" * size] * (size - len(rows))
    return RouteMap(
        size=size,
        cost={0: [[None if c == "#" else STEP for c in row] for row in rows]},
        open={0: [[c != "#" for c in row] for row in rows]},
        water={0: [[c == "~" for c in row] for row in rows]},
        guard={0: [[0] * size for _ in range(size)]},
        docks=docks,
    )


def _at(x: int, y: int = 0) -> Spot:
    return Spot(0, x, y)


CORRIDOR = grid_route(["." * 31])
HOMES = {0: _at(0), 1: _at(30)}


def test_a_door_rises_until_the_enemies_stand_a_week_apart() -> None:
    cut = cut_rivals(CORRIDOR, TOLL, [RivalDoor(_at(15), 1)], HOMES, [(0, 1)])
    assert cut.levels == (5,)
    assert cut.short == ()


def test_the_strongest_door_on_the_route_rises() -> None:
    doors = [RivalDoor(_at(10), 2), RivalDoor(_at(20), 3)]
    cut = cut_rivals(CORRIDOR, TOLL, doors, HOMES, [(0, 1)])
    assert cut.levels == (2, 5)


def test_a_capped_door_stays_at_its_cap() -> None:
    cut = cut_rivals(CORRIDOR, TOLL, [RivalDoor(_at(15), 2, cap=2)], HOMES, [(0, 1)])
    assert cut.levels == (2,)
    assert cut.short == (ShortPair((0, 1), 4, Shortfall.CAPPED),)


def test_a_route_by_sea_stays_short_and_no_door_rises() -> None:
    route = grid_route(["." + "~" * 5 + ".", "......."], docks=frozenset({_at(1)}))
    homes = {0: _at(0), 1: _at(6)}
    cut = cut_rivals(route, TOLL, [RivalDoor(_at(3, 1), 3)], homes, [(0, 1)])
    assert cut.levels == (3,)
    assert cut.short == (ShortPair((0, 1), 2, Shortfall.SEA),)


def test_a_door_at_the_top_level_leaves_the_pair_short() -> None:
    cut = cut_rivals(CORRIDOR, FLAT_TOLL, [RivalDoor(_at(15), 6)], HOMES, [(0, 1)])
    assert cut.levels == (7,)
    assert cut.short == (ShortPair((0, 1), 3, Shortfall.TOP),)


def test_a_route_with_no_door_stays_short() -> None:
    cut = cut_rivals(CORRIDOR, TOLL, [], HOMES, [(0, 1)])
    assert cut.short == (ShortPair((0, 1), 2, Shortfall.OPEN),)


def test_allies_are_never_cut_apart() -> None:
    assert enemy_pairs(4, (0, 0, 1, 1)) == [(0, 2), (0, 3), (1, 2), (1, 3)]
    assert enemy_pairs(3) == [(0, 1), (0, 2), (1, 2)]


def test_a_door_guard_watches_the_land_around_it() -> None:
    route = with_guards(grid_route(["...~", "...~", "...~"]), [(_at(2, 1), 4)])
    assert route.guard[0][1][1] == 4
    assert route.guard[0][1][3] == 0
    assert route.guard[0][1][0] == 0

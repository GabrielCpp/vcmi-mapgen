from typing import cast

from vcmi_mapgen.core.reading.effort import Effort, effort_map
from vcmi_mapgen.core.reading.routes import RouteMap, Spot

TOLL = (0, 3, 5, 8, 12, 18, 28, 45)
STEP = {".": 100 / 1500, "G": 100 / 1500, "s": 150 / 1500, "~": 100 / 1500, "#": None}


def grid_route(
    rows: list[str],
    guard: dict[tuple[int, int], int] | None = None,
    **crossings: object,
) -> RouteMap:
    size = max(len(rows), len(rows[0]))
    rows = [r.ljust(size, "#") for r in rows] + ["#" * size] * (size - len(rows))
    cost = {0: [[STEP[c] for c in row] for row in rows]}
    levels = {0: [[0] * size for _ in range(size)]}
    for (x, y), level in (guard or {}).items():
        levels[0][y][x] = level
    return RouteMap(
        size=size,
        cost=cost,
        open={0: [[c != "#" for c in row] for row in rows]},
        water={0: [[c == "~" for c in row] for row in rows]},
        guard=levels,
        **crossings,  # pyright: ignore[reportArgumentType]
    )


def _at(x: int, y: int) -> Spot:
    return Spot(0, x, y)


def test_fifteen_grass_steps_take_one_day() -> None:
    route = grid_route(["." * 16])
    effort = effort_map(route, [_at(0, 0)], TOLL)
    assert effort.at(_at(15, 0)) == Effort(days=1, guard=0, total=1)
    assert effort.at(_at(0, 0)) == Effort(days=0, guard=0, total=0)


def test_sand_slows_the_hero() -> None:
    effort = effort_map(grid_route(["s" * 12]), [_at(0, 0)], TOLL)
    assert effort.at(_at(10, 0)) == Effort(days=1, guard=0, total=1)
    assert effort.at(_at(11, 0)) == Effort(days=2, guard=0, total=2)


def test_rock_is_never_reached() -> None:
    effort = effort_map(grid_route(["..#.."]), [_at(0, 0)], TOLL)
    assert effort.at(_at(4, 0)) is None


def test_the_nearest_home_counts() -> None:
    effort = effort_map(grid_route(["." * 40]), [_at(0, 0), _at(39, 0)], TOLL)
    assert effort.at(_at(37, 0)) == Effort(days=1, guard=0, total=1)


def test_a_gate_needs_the_key_from_its_tent() -> None:
    rows = ["." * 40, "G" + "#" * 39, "." * 40]
    route = grid_route(rows, gates={_at(0, 1): 2}, tents={_at(39, 0): 2})
    effort = effort_map(route, [_at(0, 0)], TOLL)
    assert effort.at(_at(0, 2)) == Effort(days=6, guard=0, total=6)


def test_a_gate_without_its_tent_stays_shut() -> None:
    rows = [".", ".", "."]
    route = grid_route(rows, gates={_at(0, 1): 2})
    effort = effort_map(route, [_at(0, 0)], TOLL)
    assert effort.at(_at(0, 2)) is None


def test_the_hero_walks_around_a_dragon() -> None:
    rows = ["." * 30, "." + "#" * 28 + ".", "." * 30]
    route = grid_route(rows, guard={(0, 1): 7})
    effort = effort_map(route, [_at(1, 0)], TOLL)
    assert effort.at(_at(0, 2)) == Effort(days=4, guard=0, total=4)


def test_a_cheap_guard_beats_a_long_detour() -> None:
    rows = ["." * 60, "." + "#" * 58 + ".", "." * 60]
    route = grid_route(rows, guard={(0, 1): 1})
    effort = effort_map(route, [_at(0, 0)], TOLL)
    assert effort.at(_at(0, 2)) == Effort(days=1, guard=1, total=4)


def test_boarding_and_landing_each_end_a_day() -> None:
    rows = [".~~~."]
    route = grid_route(rows, docks=frozenset({_at(1, 0)}))
    effort = effort_map(route, [_at(0, 0)], TOLL)
    assert effort.at(_at(3, 0)) == Effort(days=2, guard=0, total=2)
    assert effort.at(_at(4, 0)) == Effort(days=2, guard=0, total=2)


def test_water_without_a_dock_stays_out_of_reach() -> None:
    effort = effort_map(grid_route([".~~~."]), [_at(0, 0)], TOLL)
    assert effort.at(_at(4, 0)) is None


def test_a_teleport_carries_the_hero_to_its_twin() -> None:
    rows = ["..#.."]
    jumps = {_at(1, 0): (_at(3, 0),), _at(3, 0): (_at(1, 0),)}
    effort = effort_map(grid_route(rows, jumps=jumps), [_at(0, 0)], TOLL)
    assert effort.at(_at(4, 0)) == Effort(days=1, guard=0, total=1)


def test_the_way_leads_home_first() -> None:
    effort = effort_map(grid_route(["." * 6]), [_at(0, 0)], TOLL)
    assert effort.way(_at(5, 0)) == [_at(x, 0) for x in range(5)]


def test_the_way_walks_around_a_dragon() -> None:
    rows = ["." * 30, "." + "#" * 28 + ".", "." * 30]
    route = grid_route(rows, guard={(0, 1): 7})
    way = effort_map(route, [_at(1, 0)], TOLL).way(_at(0, 2))
    assert way[0] == _at(1, 0)
    assert _at(0, 1) not in way
    assert _at(29, 1) in way


def test_the_way_crosses_a_teleport() -> None:
    jumps = {_at(1, 0): (_at(3, 0),), _at(3, 0): (_at(1, 0),)}
    effort = effort_map(grid_route(["..#..."], jumps=jumps), [_at(0, 0)], TOLL)
    assert effort.way(_at(5, 0)) == [_at(0, 0), _at(1, 0), _at(3, 0), _at(4, 0)]


def test_no_way_to_an_unreached_door() -> None:
    effort = effort_map(grid_route(["..#.."]), [_at(0, 0)], TOLL)
    assert effort.way(_at(4, 0)) == []


def test_an_object_beside_the_spot_lengthens_the_walk() -> None:
    effort = effort_map(grid_route(["." * 16, "." * 16]), [_at(0, 0)], TOLL)
    assert effort.at(_at(15, 0)) == Effort(days=1, guard=0, total=1)
    assert effort.beside(_at(15, 0), 0, {_at(14, 0)}) == Effort(days=2, guard=0, total=2)


def test_an_object_closing_the_corridor_shuts_the_spot() -> None:
    effort = effort_map(grid_route(["." * 16]), [_at(0, 0)], TOLL)
    assert effort.beside(_at(15, 0), 0, {_at(14, 0)}) is None


def test_the_guard_on_the_spot_adds_its_toll() -> None:
    effort = effort_map(grid_route(["." * 16]), [_at(0, 0)], TOLL)
    assert effort.beside(_at(15, 0), 1, set()) == Effort(days=1, guard=1, total=4)


def test_a_guard_no_stronger_than_the_way_costs_nothing_more() -> None:
    rows = ["." * 60, "." + "#" * 58 + ".", "." * 60]
    effort = effort_map(grid_route(rows, guard={(0, 1): 1}), [_at(0, 0)], TOLL)
    assert effort.visit(_at(0, 2), 1) == Effort(days=1, guard=1, total=4)
    assert effort.visit(_at(0, 2), 2) == Effort(days=1, guard=2, total=6)


def test_visits_price_every_door_as_visit_does() -> None:
    rows = ["." * 20, "." + "#" * 18 + ".", "....~~~~~~~~........", "#" * 19 + "."]
    route = grid_route(rows, guard={(0, 1): 1, (19, 1): 3}, docks=frozenset({_at(3, 2)}))
    effort = effort_map(route, [_at(0, 0)], TOLL)
    doors = [_at(x, y) for y in range(20) for x in range(20)]
    table = cast(list[list[int]], effort.visits(doors, 4).tolist())
    for least in range(5):
        expect = [-1 if (e := effort.visit(d, least)) is None else e.total for d in doors]
        assert table[least] == expect


def test_the_path_ends_on_the_tile_itself() -> None:
    effort = effort_map(grid_route(["." * 6]), [_at(0, 0)], TOLL)
    assert effort.path(_at(5, 0)) == [_at(x, 0) for x in range(6)]


def test_the_path_pays_a_cheap_guard_over_a_long_detour() -> None:
    rows = ["." * 60, "." + "#" * 58 + ".", "." * 60]
    route = grid_route(rows, guard={(0, 1): 1})
    path = effort_map(route, [_at(0, 0)], TOLL).path(_at(0, 2))
    assert path == [_at(0, 0), _at(0, 1), _at(0, 2)]

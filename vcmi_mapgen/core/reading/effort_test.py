from vcmi_mapgen.core.reading.effort import Effort, effort_map
from vcmi_mapgen.core.reading.routes import RouteMap, Spot

TOLL = (0, 3, 5, 8, 12, 18, 28, 45)
STEP = {".": 100 / 1500, "G": 100 / 1500, "s": 150 / 1500, "~": 100 / 1500, "#": None}


def _route(
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
    route = _route(["." * 16])
    effort = effort_map(route, [_at(0, 0)], TOLL)
    assert effort.at(_at(15, 0)) == Effort(days=1, guard=0, total=1)
    assert effort.at(_at(0, 0)) == Effort(days=0, guard=0, total=0)


def test_sand_slows_the_hero() -> None:
    effort = effort_map(_route(["s" * 12]), [_at(0, 0)], TOLL)
    assert effort.at(_at(10, 0)) == Effort(days=1, guard=0, total=1)
    assert effort.at(_at(11, 0)) == Effort(days=2, guard=0, total=2)


def test_rock_is_never_reached() -> None:
    effort = effort_map(_route(["..#.."]), [_at(0, 0)], TOLL)
    assert effort.at(_at(4, 0)) is None


def test_the_nearest_home_counts() -> None:
    effort = effort_map(_route(["." * 40]), [_at(0, 0), _at(39, 0)], TOLL)
    assert effort.at(_at(37, 0)) == Effort(days=1, guard=0, total=1)


def test_a_gate_needs_the_key_from_its_tent() -> None:
    rows = ["." * 40, "G" + "#" * 39, "." * 40]
    route = _route(rows, gates={_at(0, 1): 2}, tents={_at(39, 0): 2})
    effort = effort_map(route, [_at(0, 0)], TOLL)
    assert effort.at(_at(0, 2)) == Effort(days=6, guard=0, total=6)


def test_a_gate_without_its_tent_stays_shut() -> None:
    rows = [".", ".", "."]
    route = _route(rows, gates={_at(0, 1): 2})
    effort = effort_map(route, [_at(0, 0)], TOLL)
    assert effort.at(_at(0, 2)) is None


def test_the_hero_walks_around_a_dragon() -> None:
    rows = ["." * 30, "." + "#" * 28 + ".", "." * 30]
    route = _route(rows, guard={(0, 1): 7})
    effort = effort_map(route, [_at(1, 0)], TOLL)
    assert effort.at(_at(0, 2)) == Effort(days=4, guard=0, total=4)


def test_a_cheap_guard_beats_a_long_detour() -> None:
    rows = ["." * 60, "." + "#" * 58 + ".", "." * 60]
    route = _route(rows, guard={(0, 1): 1})
    effort = effort_map(route, [_at(0, 0)], TOLL)
    assert effort.at(_at(0, 2)) == Effort(days=1, guard=1, total=4)


def test_boarding_and_landing_each_end_a_day() -> None:
    rows = [".~~~."]
    route = _route(rows, docks=frozenset({_at(1, 0)}))
    effort = effort_map(route, [_at(0, 0)], TOLL)
    assert effort.at(_at(3, 0)) == Effort(days=2, guard=0, total=2)
    assert effort.at(_at(4, 0)) == Effort(days=2, guard=0, total=2)


def test_water_without_a_dock_stays_out_of_reach() -> None:
    effort = effort_map(_route([".~~~."]), [_at(0, 0)], TOLL)
    assert effort.at(_at(4, 0)) is None


def test_a_teleport_carries_the_hero_to_its_twin() -> None:
    rows = ["..#.."]
    jumps = {_at(1, 0): (_at(3, 0),), _at(3, 0): (_at(1, 0),)}
    effort = effort_map(_route(rows, jumps=jumps), [_at(0, 0)], TOLL)
    assert effort.at(_at(4, 0)) == Effort(days=1, guard=0, total=1)

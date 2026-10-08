from vcmi_mapgen.core.reading.effort import effort_map
from vcmi_mapgen.core.reading.routes import RouteMap, Spot
from vcmi_mapgen.core.steps.gameplay.sea_links import SeaLinks, sea_way, seas, walked

NO_DOCKS: frozenset[Spot] = frozenset()
TOLL = (0, 3, 5, 8, 12, 18, 28, 45)
ISLANDS = ["..~~~..", "..~~~..", "..~~~.."]


def _route(
    rows: list[str], docks: frozenset[Spot] = NO_DOCKS, guard: dict[Spot, int] | None = None
) -> RouteMap:
    size = max(len(rows), len(rows[0]))
    rows = [r.ljust(size, "#") for r in rows] + ["#" * size] * (size - len(rows))
    levels = [[0] * size for _ in range(size)]
    for s, level in (guard or {}).items():
        levels[s.y][s.x] = level
    return RouteMap(
        size=size,
        cost={0: [[None if c == "#" else 0.07 for c in row] for row in rows]},
        open={0: [[c != "#" for c in row] for row in rows]},
        water={0: [[c == "~" for c in row] for row in rows]},
        guard={0: levels},
        docks=docks,
    )


def _at(x: int, y: int) -> Spot:
    return Spot(0, x, y)


def test_a_hero_walks_from_beside_a_closed_town_up_to_the_water() -> None:
    route = _route(["#.~"])
    assert walked(route, [_at(0, 0)], 0) == {_at(1, 0)}


def test_a_guard_above_the_ceiling_stops_the_walk() -> None:
    route = _route(["...."], guard={_at(2, 0): 2})
    assert walked(route, [_at(0, 0)], 1) == {_at(0, 0), _at(1, 0)}
    assert _at(3, 0) in walked(route, [_at(0, 0)], 2)


def test_two_bodies_of_water_are_two_seas() -> None:
    sea_of = seas(_route(["~.~"]))
    assert sea_of[_at(0, 0)] != sea_of[_at(2, 0)]


def test_a_dock_beside_the_first_land_links_it_to_the_land_across_the_sea() -> None:
    links = SeaLinks(_route(ISLANDS, docks=frozenset({_at(2, 1)})), [[_at(0, 0)], [_at(6, 0)]])
    assert links.apart() == [(0, 1), (1, 0)]
    assert links.linked(0, 1)
    assert links.unlinked() == [(1, 0)]


def test_players_on_one_land_are_never_unlinked() -> None:
    links = SeaLinks(_route(["......."]), [[_at(0, 0)], [_at(6, 0)]])
    assert links.joined(0, 1)
    assert links.unlinked() == []


def test_a_boarding_fits_when_its_sea_lands_on_the_rival() -> None:
    links = SeaLinks(_route(["..~~~..", "#######", "~~....."]), [[_at(0, 0)], [_at(6, 0)]])
    fit = links.fit(1, links.land(0))
    assert fit(((2, 0), (1, 0)))
    assert not fit(((0, 2), (1, 0)))
    assert not fit(((2, 0), (5, 0)))


def test_the_sea_way_sails_from_the_dock_to_the_rival_town() -> None:
    route = _route(ISLANDS, docks=frozenset({_at(2, 1)}))
    way = sea_way(effort_map(route, [_at(0, 1)], TOLL), [_at(6, 1)])
    assert way[0] == _at(0, 1)
    assert any(route.water[0][s.y][s.x] for s in way)
    assert way[-1] in {_at(5, 0), _at(5, 1), _at(5, 2), _at(6, 0), _at(6, 2)}

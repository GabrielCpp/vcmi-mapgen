from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState, PlacedObject
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.reading.routes import Spot, route_map

SIZE = 8
MONSTER = "avwmon3"
GATE = "avxbgt00"
TENT = "avxkey00"
SHIPYARD = "avxshyd0"
MONOLITH = "avxmn2g0"
CAVE = "avtcave"
SIGN = "avxsndg0"
GOLD = "avtgold0"


def _put(catalog: Catalog, kind: str, x: int, y: int) -> PlacedObject:
    return PlacedObject.at(catalog.identity_of(kind), (x, y), purpose=Purpose.UNKNOWN)


def _state(objs: list[PlacedObject], water_from: int = SIZE) -> MapState:
    grid = [
        [Terrain.WATER if x >= water_from else Terrain.GRASS for x in range(SIZE)]
        for _ in range(SIZE)
    ]
    return MapState(size=SIZE, terrain={0: grid}, objs=objs)


def test_a_monster_guards_the_land_around_it_and_not_the_sea(catalog: Catalog) -> None:
    route = route_map(catalog, _state([_put(catalog, MONSTER, 4, 3)], water_from=5))
    guarded = {(x, y) for y in range(SIZE) for x in range(SIZE) if route.guard[0][y][x]}
    assert guarded == {(x, y) for x in (3, 4) for y in (2, 3, 4)}
    assert route.guard[0][3][4] == 3
    assert route.open[0][3][4]


def test_a_gate_opens_only_its_entrance_and_names_its_key(catalog: Catalog) -> None:
    route = route_map(catalog, _state([_put(catalog, GATE, 4, 3), _put(catalog, TENT, 6, 6)]))
    assert route.gates == {Spot(0, 3, 3): 0}
    assert route.tents == {Spot(0, 6, 6): 0}
    assert route.open[0][3][3]
    assert not route.open[0][3][2]
    assert not route.open[0][3][4]


def test_a_shipyard_docks_the_water_beside_it(catalog: Catalog) -> None:
    route = route_map(catalog, _state([_put(catalog, SHIPYARD, 4, 3)], water_from=5))
    assert route.docks == {Spot(0, 5, y) for y in (2, 3, 4)}
    assert not route.open[0][3][3]


def test_two_monoliths_of_one_channel_lead_to_each_other(catalog: Catalog) -> None:
    route = route_map(
        catalog, _state([_put(catalog, MONOLITH, 1, 1), _put(catalog, MONOLITH, 6, 6)])
    )
    assert route.jumps == {Spot(0, 1, 1): (Spot(0, 6, 6),), Spot(0, 6, 6): (Spot(0, 1, 1),)}


def test_rock_costs_nothing_and_no_hero_stands_on_it(catalog: Catalog) -> None:
    state = _state([])
    state.terrain[0][0][0] = Terrain.ROCK
    state.terrain[0][0][1] = Terrain.SWAMP
    route = route_map(catalog, state)
    assert route.cost[0][0][0] is None
    assert not route.open[0][0][0]
    assert route.cost[0][0][1] == 175 / 1500


def test_a_subterranean_gate_keeps_its_entrance_open_on_both_levels(catalog: Catalog) -> None:
    cave = [_put(catalog, CAVE, 4, 3), _put(catalog, CAVE, 4, 3)]
    cave[1].level = 1
    state = _state(cave)
    state.terrain[1] = [row[:] for row in state.terrain[0]]
    state.gate_blk = {lvl: frozenset({(3, 3), (2, 2)}) for lvl in (0, 1)}
    route = route_map(catalog, state)
    assert route.open[0][3][3] and route.open[1][3][3]
    assert not route.open[0][2][2]
    assert route.jumps[Spot(0, 3, 3)] == (Spot(1, 3, 3),)


def test_a_sign_lasts_and_closes_its_visit_tile(catalog: Catalog) -> None:
    route = route_map(catalog, _state([_put(catalog, SIGN, 4, 3)]))
    assert not route.open[0][3][4]
    assert route.open[0][4][4]


def test_a_resource_vanishes_and_leaves_its_tile_open(catalog: Catalog) -> None:
    route = route_map(catalog, _state([_put(catalog, GOLD, 4, 3)]))
    assert route.open[0][3][4]

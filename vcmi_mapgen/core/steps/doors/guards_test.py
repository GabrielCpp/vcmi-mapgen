import random

from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.planning.door_levels import DEFAULT_DOOR_LEVEL, TOP_LEVEL, DoorSpread
from vcmi_mapgen.core.reading.places import PlaceRole
from vcmi_mapgen.core.steps.doors.guards import (
    door_level,
    door_tile,
    home_doors,
    home_land,
    home_reach,
    home_room,
    open_zones,
    player_door_cap,
    territory_areas,
)
from vcmi_mapgen.core.steps.terrain_gen.result import PlannedDoor, PlannedPlace, TerritoryPlan

PLAYER_DOOR = PlannedDoor((0, 1), (0, 1), (0, None), ((4, 2), (5, 2)))
NEUTRAL_DOOR = PlannedDoor((1, 2), (1, 2), (None, None), ((9, 2), (9, 3)))
SPREAD = DoorSpread(player=(2, 2), neutral=(0, 6, 9))


def test_a_door_out_of_a_player_territory_draws_from_the_player_doors() -> None:
    assert door_level(SPREAD, PLAYER_DOOR, random.Random(1)) == 2


def test_a_door_between_neutral_territories_draws_a_level_from_1_to_7() -> None:
    assert door_level(SPREAD, NEUTRAL_DOOR, random.Random(1)) == 6


CHAIN = TerritoryPlan(
    zones={0: 0, 1: 1, 2: 2, 3: 3},
    owners=(0, None, None, None),
    doors=(
        PlannedDoor((0, 1), (0, 1), (0, None), ((4, 2), (5, 2))),
        PlannedDoor((1, 2), (1, 2), (None, None), ((9, 2), (9, 3))),
        PlannedDoor((2, 3), (2, 3), (None, None), ((9, 7), (9, 8))),
    ),
)


def test_a_door_draws_no_level_past_its_cap() -> None:
    spread = DoorSpread(player=(2, 5, 6, 7))
    assert door_level(spread, PLAYER_DOOR, random.Random(1), cap=3) == 2


def test_the_home_reach_stops_once_the_land_holds_the_room() -> None:
    assert home_reach(0, CHAIN.doors, {0: 100, 1: 100, 2: 500, 3: 900}, 600) == (2, (0, 1))
    assert home_reach(0, CHAIN.doors, {0: 700}, 600) == (0, ())


PAIR = TerritoryPlan(
    zones={0: 0, 1: 1, 2: 2, 3: 3},
    owners=(0, None, None, 1),
    doors=CHAIN.doors[:2],
)


def test_the_home_room_is_the_mean_home() -> None:
    assert home_room(PAIR, {0: 100, 1: 900, 3: 500}) == 300


def test_a_cramped_home_leaves_its_door_open() -> None:
    assert home_doors(PAIR, {0: 100, 1: 300, 3: 500}) == {0}


def test_a_cramped_home_leaves_open_every_door_it_crosses_to_the_room() -> None:
    assert home_doors(PAIR, {0: 100, 1: 100, 2: 150, 3: 500}) == {0, 1}


def test_a_door_that_overshoots_the_room_more_than_it_closes_stays_guarded() -> None:
    assert home_doors(PAIR, {0: 100, 1: 900, 3: 500}) == frozenset()


def test_a_home_as_roomy_as_its_rivals_keeps_its_door_guarded() -> None:
    assert home_doors(PAIR, {0: 500, 1: 100, 3: 500}) == frozenset()


def test_the_areas_count_each_territory_tiles() -> None:
    assert territory_areas(((0, 0, -1), (1, 2, 2)), {0: 0, 1: 0, 2: 1}) == {0: 3, 1: 2}


def test_an_empty_spread_falls_back_to_the_default_level() -> None:
    assert door_level(DoorSpread(), PLAYER_DOOR, random.Random(1)) == DEFAULT_DOOR_LEVEL


def test_loot_zones_and_dead_end_treasure_places_stay_open() -> None:
    places = {
        0: PlannedPlace(PlaceRole.HOME, 0, Terrain.GRASS),
        3: PlannedPlace(PlaceRole.TREASURE, None, Terrain.DIRT),
    }
    door = PlannedDoor((0, 3), (0, 3), (0, None), ((4, 2), (5, 2)))
    plan = TerritoryPlan({0: 0, 3: 3}, (0, None, None, None), (door,))
    assert open_zones(places, {7}, plan) == {3, 7}


def test_a_treasure_place_with_two_doors_takes_guards() -> None:
    places = {3: PlannedPlace(PlaceRole.TREASURE, None, Terrain.DIRT)}
    doors = (
        PlannedDoor((0, 3), (0, 3), (0, None), ((4, 2), (5, 2))),
        PlannedDoor((3, 4), (3, 4), (None, None), ((8, 2), (9, 2))),
    )
    plan = TerritoryPlan({0: 0, 3: 3, 4: 4}, (0, None, None, None, None), doors)
    assert open_zones(places, set(), plan) == set()


def test_a_treasure_place_inside_a_larger_territory_takes_guards() -> None:
    places = {3: PlannedPlace(PlaceRole.TREASURE, 1, Terrain.DIRT)}
    door = PlannedDoor((0, 3), (0, 1), (0, 1), ((4, 2), (5, 2)))
    plan = TerritoryPlan({0: 0, 3: 1, 5: 1}, (0, 1), (door,))
    assert open_zones(places, set(), plan) == set()


def test_the_guard_takes_the_first_door_tile_it_fits_on() -> None:
    assert door_tile(PLAYER_DOOR, lambda t: t != (4, 2)) == (5, 2)
    assert door_tile(PLAYER_DOOR, lambda _t: False) is None


def test_a_home_door_stays_guarded_when_it_would_join_two_players() -> None:
    plan = TerritoryPlan(
        zones={0: 0, 1: 1, 2: 2},
        owners=(0, None, 1),
        doors=(
            PlannedDoor((0, 1), (0, 1), (0, None), ((4, 2), (5, 2))),
            PlannedDoor((1, 2), (1, 2), (None, 1), ((9, 2), (9, 3))),
        ),
    )
    assert home_doors(plan, {0: 10, 1: 10, 2: 1000}) == {0}


TOLL = (0, 3, 5, 8, 12, 18, 28, 45)


def test_a_door_out_of_a_player_territory_leaves_days_to_reach_the_mines() -> None:
    assert player_door_cap(PLAYER_DOOR, {0}, TOLL, 14) == 3


def test_a_door_between_neutral_territories_takes_any_level() -> None:
    assert player_door_cap(NEUTRAL_DOOR, {0}, TOLL, 14) == TOP_LEVEL


def test_a_door_past_the_open_land_of_a_home_leaves_days_to_reach_the_mines() -> None:
    land = home_land(CHAIN, {0})
    assert land == {0, 1}
    assert player_door_cap(CHAIN.doors[1], land, TOLL, 14) == 3
    assert player_door_cap(CHAIN.doors[2], land, TOLL, 14) == TOP_LEVEL

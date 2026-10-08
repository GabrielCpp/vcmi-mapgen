import random

from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.priors.territories import TerritoryStats
from vcmi_mapgen.core.reading.places import PlaceRole
from vcmi_mapgen.core.steps.doors.guards import (
    DEFAULT_DOOR_LEVEL,
    door_caps,
    door_level,
    door_tile,
    home_reach,
    open_zones,
    territory_areas,
)
from vcmi_mapgen.core.steps.terrain_gen.result import PlannedDoor, PlannedPlace, TerritoryPlan

PLAYER_DOOR = PlannedDoor((0, 1), (0, 1), (0, None), ((4, 2), (5, 2)))
NEUTRAL_DOOR = PlannedDoor((1, 2), (1, 2), (None, None), ((9, 2), (9, 3)))
STATS = TerritoryStats(player_door_levels=(2, 2), neutral_door_levels=(0, 6, 9))


def test_a_door_out_of_a_player_territory_draws_from_the_player_doors() -> None:
    assert door_level(STATS, PLAYER_DOOR, random.Random(1)) == 2


def test_a_door_between_neutral_territories_draws_a_level_from_1_to_7() -> None:
    assert door_level(STATS, NEUTRAL_DOOR, random.Random(1)) == 6


TOLL = (0, 3, 5, 8, 12, 18, 28, 45)
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
    stats = TerritoryStats(player_door_levels=(2, 5, 6, 7))
    assert door_level(stats, PLAYER_DOOR, random.Random(1), cap=3) == 2


def test_the_home_reach_stops_once_the_land_holds_the_room() -> None:
    assert home_reach(0, CHAIN.doors, {0: 100, 1: 100, 2: 300, 3: 900}) == (2, (0, 1))
    assert home_reach(0, CHAIN.doors, {0: 500}) == (0, ())


def test_a_roomy_home_caps_its_door_so_one_toll_leaves_the_travel_days() -> None:
    assert door_caps(CHAIN, {0: 100, 1: 900}, TOLL, 14) == {0: 3}


def test_a_cramped_home_shares_the_days_between_the_doors_it_crosses() -> None:
    assert door_caps(CHAIN, {0: 100, 1: 100, 2: 300}, TOLL, 14) == {0: 2, 1: 2}


def test_the_areas_count_each_territory_tiles() -> None:
    assert territory_areas(((0, 0, -1), (1, 2, 2)), {0: 0, 1: 0, 2: 1}) == {0: 3, 1: 2}


def test_an_empty_spread_falls_back_to_the_default_level() -> None:
    assert door_level(TerritoryStats(), PLAYER_DOOR, random.Random(1)) == DEFAULT_DOOR_LEVEL


def test_loot_zones_and_dead_end_treasure_places_stay_open() -> None:
    places = {
        0: PlannedPlace(PlaceRole.HOME, 0, Terrain.GRASS),
        3: PlannedPlace(PlaceRole.TREASURE, None, Terrain.DIRT),
    }
    door = PlannedDoor((0, 3), (0, 3), (0, None), ((4, 2), (5, 2)))
    assert open_zones(places, {7}, [door]) == {3, 7}


def test_a_treasure_place_with_two_doors_takes_guards() -> None:
    places = {3: PlannedPlace(PlaceRole.TREASURE, None, Terrain.DIRT)}
    doors = [
        PlannedDoor((0, 3), (0, 3), (0, None), ((4, 2), (5, 2))),
        PlannedDoor((3, 4), (3, 4), (None, None), ((8, 2), (9, 2))),
    ]
    assert open_zones(places, set(), doors) == set()


def test_the_guard_takes_the_first_door_tile_it_fits_on() -> None:
    assert door_tile(PLAYER_DOOR, lambda t: t != (4, 2)) == (5, 2)
    assert door_tile(PLAYER_DOOR, lambda _t: False) is None

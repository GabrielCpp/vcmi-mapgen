"""The reading vector on a small literal map, on literal content rows and on a literal
territory reading."""

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Footprint, MapState, PlacedObject, Role
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.road import Road
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.priors.places import PlaceContent
from vcmi_mapgen.core.reading.content import UNREACHED
from vcmi_mapgen.core.reading.territories import TerritoryReading
from vcmi_mapgen.core.reading.vector import by_hop, map_vector, territory_vector

WIDTH = 15
HEIGHT = 7
WALL_X = 7
GAP_Y = 3
LEFT_TOWN = (2, 3)
RIGHT_TOWN = (12, 3)


def _obj(t: tuple[int, int], purpose: str, role: Role) -> PlacedObject:
    return PlacedObject(t[0], t[1], 0, purpose, purpose.lower(), Footprint.one(role))


def _state(terrain: Terrain) -> MapState:
    wall = [
        _obj((WALL_X, y), Purpose.DECORATION, Role.BLOCKING) for y in range(HEIGHT) if y != GAP_Y
    ]
    towns = [_obj(t, Purpose.TOWN, Role.VISIT) for t in (LEFT_TOWN, RIGHT_TOWN)]
    grid = [[terrain] * WIDTH for _ in range(HEIGHT)]
    roads = {0: {(x, GAP_Y): Road.DIRT for x in range(3, 12)}}
    return MapState(size=WIDTH, terrain={0: grid}, objs=wall + towns, roads=roads)


def _row(hop: int, area: int, value: int, guards: tuple[int, ...]) -> PlaceContent:
    return PlaceContent("middle", hop, area, 1, value, guards, 0)


def test_by_hop_groups_value_and_guard_level_by_capped_hop() -> None:
    rows = [
        _row(0, 10, 0, ()),
        _row(1, 10, 100, (2,)),
        _row(1, 30, 300, (4,)),
        _row(5, 20, 400, (6,)),
        _row(UNREACHED, 50, 900, (7,)),
    ]
    assert by_hop(rows) == {
        "value_hop0": 0.0,
        "value_hop1": 10.0,
        "guard_hop1": 3,
        "value_hop4": 20.0,
        "guard_hop4": 6,
    }


def test_a_narrow_gap_reads_as_one_palette_and_a_gated_border(catalog: Catalog) -> None:
    vector = map_vector(catalog, _state(Terrain.GRASS), {(*LEFT_TOWN, 0): 0, (*RIGHT_TOWN, 0): 1})
    land = WIDTH * HEIGHT
    walk = land - (HEIGHT - 1)
    assert vector["palette_regions"] == 1
    assert vector["same_share"] == 1
    assert vector["gated_share"] == 1
    assert vector["open_share"] == 0
    assert vector["closed_share"] == 0
    assert vector["walk_share"] == walk / land
    assert vector["road_share"] == 9 / walk
    assert vector["guards_per_100_land"] == 0
    assert vector["home_separation"] > 0


def test_a_map_without_land_reads_empty(catalog: Catalog) -> None:
    assert map_vector(catalog, _state(Terrain.WATER), {}) == {}


def test_territory_readings_take_means_of_counts_and_medians_of_levels() -> None:
    reading = TerritoryReading((1, 2), (1, 1, 4), (1, 2), (2, 3, 7), ())
    assert territory_vector(reading) == {
        "zones_player_terr": 1.5,
        "zones_neutral_terr": 2,
        "doors_per_pair": 1.5,
        "door_level_player": 3,
    }

"""Tests for the level the roads read."""

import random

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Footprint, PlacedObject, Role, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.road import Road
from vcmi_mapgen.core.priors.places import RoadStats
from vcmi_mapgen.core.steps.roads.sites import homes_of, map_surface, shy_of, visit_tile

TOWN = Footprint(
    3,
    2,
    (
        (-2, -1, Role.BLOCKING),
        (-1, -1, Role.BLOCKING),
        (0, -1, Role.BLOCKING),
        (-2, 0, Role.BLOCKING),
        (-1, 0, Role.ENTRANCE),
        (0, 0, Role.BLOCKING),
    ),
)
PILE = Footprint.one(Role.VISIT)
SHRINE = Footprint(
    2,
    2,
    (
        (-1, -1, Role.OVERLAY),
        (0, -1, Role.OVERLAY),
        (-1, 0, Role.BLOCKING),
        (0, 0, Role.ENTRANCE),
        (0, 1, Role.APPROACH),
    ),
)


def _obj(fp: Footprint, x: int, y: int) -> PlacedObject:
    return PlacedObject(x, y, 0, "TOWN", "town", fp)


def _walk(blocked: set[Tile]) -> frozenset[Tile]:
    return frozenset((x, y) for x in range(10) for y in range(10) if (x, y) not in blocked)


def test_visit_tile_prefers_the_approach_below_an_entrance() -> None:
    assert visit_tile(_obj(TOWN, 5, 5), _walk({(5, 5), (4, 5), (3, 5)})) == (4, 6)


def test_visit_tile_falls_back_to_a_walkable_visit_cell() -> None:
    assert visit_tile(_obj(PILE, 2, 2), _walk(set())) == (2, 2)


def test_visit_tile_falls_back_to_a_walkable_neighbour_of_an_interactive_cell() -> None:
    walk = _walk({(5, 5), (4, 5), (3, 5), (4, 6)})
    assert visit_tile(_obj(TOWN, 5, 5), walk) == (3, 4)


def test_homes_of_skip_a_town_outside_every_place() -> None:
    label = [[0 if y < 8 else -1 for _ in range(10)] for y in range(10)]
    walk = _walk(set())
    homes = homes_of([_obj(TOWN, 5, 5), _obj(TOWN, 5, 8)], 0, label, walk)
    assert homes == ((0, (4, 6)),)


def test_the_map_surface_is_drawn_from_the_counts_of_every_level() -> None:
    stats = [RoadStats(surface={0: {3: 4}}), RoadStats(surface={-1: {3: 1}})]
    assert map_surface(stats, random.Random(5)) == Road.COBBLESTONE


def test_the_map_surface_is_dirt_without_counts() -> None:
    assert map_surface([RoadStats()], random.Random(5)) == Road.DIRT


def test_shy_of_holds_the_walkable_sprite_of_an_object_no_road_serves(catalog: Catalog) -> None:
    shrine = PlacedObject(5, 5, 0, Purpose.STAT_PERMANENT, "shrine", SHRINE)
    walk = _walk({(4, 5), (5, 5)})
    assert shy_of(catalog, [shrine], frozenset(), walk) == {(4, 4), (5, 4)}


def test_shy_of_leaves_out_the_tile_a_road_stops_on(catalog: Catalog) -> None:
    shrine = PlacedObject(5, 5, 0, Purpose.STAT_PERMANENT, "shrine", SHRINE)
    walk = _walk({(4, 5)})
    assert shy_of(catalog, [shrine], {(5, 5)}, walk) == {(4, 4), (5, 4)}


def test_shy_of_leaves_out_decoration(catalog: Catalog) -> None:
    tree = PlacedObject(2, 2, 0, Purpose.DECORATION, "tree", SHRINE)
    walk = _walk({(1, 2), (2, 2)})
    assert shy_of(catalog, [tree], frozenset(), walk) == frozenset()

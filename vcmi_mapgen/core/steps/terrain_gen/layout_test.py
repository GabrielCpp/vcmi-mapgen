"""Tests for growing the places on land."""

import random

from vcmi_mapgen.core.steps.terrain_gen.layout import grow, home_gap, main_land, roomy


def test_grow_labels_every_land_tile_and_only_land() -> None:
    land = [[True] * 40 for _ in range(40)]
    land[0][0] = land[0][1] = False
    layout = grow(land, [(5, 5), (34, 5), (5, 34), (34, 34)], [400] * 4, random.Random(4))
    for y, row in enumerate(layout.label):
        for x, z in enumerate(row):
            assert (z >= 0) == land[y][x]
    assert layout.places == 4
    assert {z for row in layout.label for z in row if z >= 0} == {0, 1, 2, 3}


def test_grow_makes_a_pocket_of_land_no_anchor_reached() -> None:
    land = [[x != 10 for x in range(20)] for _ in range(20)]
    layout = grow(land, [(2, 2), (5, 15)], [200, 200], random.Random(1))
    assert layout.places == 3
    assert {layout.label[y][x] for y in range(20) for x in range(11, 20)} == {2}


def test_main_land_keeps_the_largest_mass() -> None:
    land = [[x != 3 for x in range(10)] for _ in range(4)]
    mass = main_land(land)
    assert all(mass[y][x] == (x > 3) for y in range(4) for x in range(10))


def test_roomy_needs_its_square_on_the_map_and_nearly_all_land() -> None:
    land = [[True] * 9 for _ in range(9)]
    land[4][4] = False
    room = roomy(land, 3)
    assert (1, 1) in room
    assert (0, 0) not in room
    assert (4, 3) not in room
    assert (4, 2) in room


def test_home_gap_walks_around_water() -> None:
    land = [[not (x == 5 and y < 9) for x in range(10)] for y in range(10)]
    assert home_gap(land, [(0, 0), (9, 0)]) == 27 / 10

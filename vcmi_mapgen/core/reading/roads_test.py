"""Tests for the road reading."""

from vcmi_mapgen.core.reading.roads import crossed_pairs, road_components, town_links


def test_road_components_join_diagonal_tiles_and_split_apart_ones() -> None:
    comp = road_components([(0, 0), (1, 1), (5, 5)])
    assert comp[(0, 0)] == comp[(1, 1)]
    assert comp[(5, 5)] != comp[(0, 0)]


def test_town_links_count_reached_and_joined_towns() -> None:
    comp = road_components([(x, 0) for x in range(2, 9)] + [(20, 20)])
    joined, linked = town_links([(0, 0), (10, 1), (21, 22), (40, 40)], comp)
    assert joined == 3
    assert linked == 2


def test_crossed_pairs_name_each_border_two_road_tiles_span() -> None:
    labels = [[0, 0, 1, 1], [0, 0, 1, 1], [-1, -1, 2, 2]]
    roads = [(1, 0), (2, 0), (3, 1)]
    assert crossed_pairs(labels, roads) == {(0, 1)}
    assert crossed_pairs(labels, [(1, 1), (0, 2)]) == set()

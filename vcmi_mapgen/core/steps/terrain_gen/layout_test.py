"""Tests for laying a place graph out on land."""

import random

from vcmi_mapgen.core.reading.places import PlaceRole
from vcmi_mapgen.core.steps.terrain_gen.layout import lay_out
from vcmi_mapgen.core.steps.terrain_gen.place_graph import PlaceGraph
from vcmi_mapgen.core.steps.terrain_gen.place_map import label_adjacency


def test_layout_partitions_land_and_realises_a_path_of_places() -> None:
    land = [[True] * 40 for _ in range(40)]
    land[0][0] = land[0][1] = False
    roles = (PlaceRole.HOME, PlaceRole.MIDDLE, PlaceRole.MIDDLE, PlaceRole.HOME)
    graph = PlaceGraph(
        roles, (0, None, None, 3), (400, 400, 400, 398), frozenset({(0, 1), (1, 2), (2, 3)})
    )
    layout = lay_out(land, graph, 0.3, random.Random(4))
    for y, row in enumerate(layout.label):
        for x, z in enumerate(row):
            assert (z >= 0) == land[y][x]
    assert layout.places == 4
    assert {z for row in layout.label for z in row if z >= 0} == {0, 1, 2, 3}
    assert not layout.missing
    assert graph.edges <= label_adjacency(layout.label)
    assert layout.home_contacts == 0

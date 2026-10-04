"""Tests for zones read from a finished label grid."""

from vcmi_mapgen.core.grid.segment import zones_of_labels
from vcmi_mapgen.core.model.terrain import Terrain


def test_two_touching_places_of_one_terrain_stay_two_zones() -> None:
    grid = [[Terrain.GRASS] * 8 for _ in range(4)]
    label = [[0] * 4 + [1] * 4 for _ in range(4)]
    zones = zones_of_labels(grid, label, {0: Terrain.GRASS, 1: Terrain.GRASS})
    assert set(zones) == {0, 1}
    assert zones[0].area == zones[1].area == 16
    assert zones[0].adjacent_zones == {1}
    assert zones[1].terrain_type == Terrain.GRASS

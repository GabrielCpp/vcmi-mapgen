import numpy as np

from vcmi_mapgen.core.priors.water import WaterTarget
from vcmi_mapgen.core.reading.water import (
    STATIC,
    WaterPlace,
    big_masses,
    edge_water_share,
    land_labels,
    neighbour_features,
    static_features,
    water_places,
    water_target,
)


def _strait() -> np.ndarray[tuple[int, int], np.dtype[np.bool_]]:
    water = np.zeros((6, 6), dtype=np.bool_)
    water[:, 3] = True
    return water


def test_a_water_column_splits_the_land_into_two_big_masses() -> None:
    water = _strait()
    assert big_masses(~water) == 2
    assert land_labels(~water)[0, 0] != land_labels(~water)[0, 5]


def test_the_edge_share_counts_the_outer_ring_once() -> None:
    assert edge_water_share(_strait()) == 2 / 20


def test_the_target_reads_share_edge_and_masses() -> None:
    water = _strait()
    assert water_target(water, np.zeros_like(water)) == WaterTarget(6 / 36, 2 / 20, 2)


def test_neighbour_shares_ignore_the_tiles_off_the_map() -> None:
    nb = neighbour_features(_strait())
    assert np.array_equal(nb[:1], [[0.0, 0.0]])
    assert np.array_equal(nb[2:3], [[1 / 3, 0.5]])


def test_each_place_gets_its_middle_tile_and_mass() -> None:
    labels = [[0, 0, 0, -1, 1, 1]] * 3
    masses = land_labels(np.array([[p >= 0 for p in row] for row in labels]))
    places = water_places(labels, masses)
    assert [p.centre for p in places] == [(1, 1), (4, 1)]
    assert places[0].mass != places[1].mass


def test_a_tile_between_two_masses_reads_as_a_strait() -> None:
    places = [WaterPlace((0, 0), 1.0, 1), WaterPlace((4, 0), 1.0, 2)]
    x = static_features((1, 5), places, [], 0.0)
    assert x.shape == (5, STATIC)
    assert x[2, 3] == 1.0

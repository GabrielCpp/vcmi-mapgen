"""The quota flood gives every land tile to one territory, each territory one piece holding
its site, with areas near their targets."""

import random
from typing import cast

import numpy as np

from vcmi_mapgen.core.grid.components import components
from vcmi_mapgen.core.grid.noise import value_noise
from vcmi_mapgen.core.grid.quota import Field, Labels, Mask, cell_areas, cell_tiles, quota_flood

SIDE = 48
SITES = [(6, 6), (40, 8), (10, 38), (38, 40), (24, 24)]
SHARES = [0.015, 0.2, 0.3, 0.285, 0.2]
TARGETS = [s * SIDE * SIDE for s in SHARES]


def _land() -> Mask:
    return np.ones((SIDE, SIDE), dtype=np.bool_)


def _noise() -> list[Field]:
    return [
        np.asarray(value_noise(SIDE, SIDE, 8, random.Random(i)), dtype=np.float64)
        for i in range(len(SITES))
    ]


def _flood(land: Mask) -> Labels:
    return quota_flood(land, SITES, TARGETS, _noise())


def test_every_land_tile_is_assigned_and_water_is_not() -> None:
    land = _land()
    land[0:3, 20:28] = False
    label = _flood(land)
    assert int(np.count_nonzero(np.less(label[land], 0))) == 0
    assert int(np.count_nonzero(np.not_equal(label[~land], -1))) == 0


def test_each_territory_is_one_piece_holding_its_site() -> None:
    label = _flood(_land())
    for i, site in enumerate(SITES):
        tiles = cell_tiles(label, i)
        assert site in tiles
        assert len(set(components(frozenset(tiles)).values())) == 1


def test_areas_land_within_ten_percent_of_their_targets() -> None:
    label = _flood(_land())
    areas = cast("list[float]", cell_areas(label, len(SITES)).tolist())
    for area, target in zip(areas, TARGETS, strict=True):
        assert abs(area - target) <= 0.1 * target


def test_the_same_input_gives_the_same_flood() -> None:
    assert np.array_equal(_flood(_land()), _flood(_land()))

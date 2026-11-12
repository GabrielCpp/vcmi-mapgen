import random
from typing import cast

import numpy as np

from vcmi_mapgen.core.steps.terrain_gen.islands import STRAIT, Labels, raise_islands

SIDE = 40


def _sea() -> Labels:
    label: Labels = np.full((SIDE, SIDE), -1, dtype=np.int64)
    label[:, :4] = 0
    return label


def _rows(label: Labels) -> list[list[int]]:
    return cast("list[list[int]]", label.tolist())


def _tiles(label: Labels, place: int) -> set[tuple[int, int]]:
    return {(x, y) for y, row in enumerate(_rows(label)) for x, v in enumerate(row) if v == place}


def test_raises_one_new_place_per_share() -> None:
    out, count = raise_islands(_sea(), (30 / SIDE**2, 20 / SIDE**2), 1, random.Random("i"))
    assert count == 3
    assert len(_tiles(out, 1)) == 30
    assert len(_tiles(out, 2)) == 20


def test_an_island_keeps_a_strait_from_other_land_and_the_edge() -> None:
    out, _ = raise_islands(_sea(), (40 / SIDE**2,), 1, random.Random("s"))
    land = _tiles(out, 0)
    for x, y in _tiles(out, 1):
        assert STRAIT <= x < SIDE - STRAIT and STRAIT <= y < SIDE - STRAIT
        assert all(abs(x - lx) + abs(y - ly) > STRAIT for lx, ly in land)


def test_a_share_under_four_tiles_is_dropped() -> None:
    sea = _sea()
    out, count = raise_islands(sea, (2 / SIDE**2,), 1, random.Random("d"))
    assert count == 1
    assert _rows(out) == _rows(sea)


def test_an_island_in_a_narrow_channel_stays_round() -> None:
    label: Labels = np.full((SIDE, SIDE), 0, dtype=np.int64)
    label[:, 14:25] = -1
    out, _ = raise_islands(label, (120 / SIDE**2,), 1, random.Random("c"))
    tiles = _tiles(out, 1)
    ys = [y for _x, y in tiles]
    assert tiles
    assert max(ys) - min(ys) <= 6

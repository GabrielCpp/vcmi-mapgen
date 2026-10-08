"""Tests for core.planning.borders (the crossings of a zone border)."""

from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.planning.borders import closing_pairs, cross_pairs


def _strip() -> tuple[set[Tile], dict[Tile, int]]:
    tiles = {(x, 0) for x in range(3)}
    return tiles, {(0, 0): 0, (1, 0): 1, (2, 0): 2}


def test_a_band_only_spares_the_crossing_toward_its_own_zone() -> None:
    tiles, owner = _strip()
    plain, banded = cross_pairs(tiles, owner, {((1, 0), 2)})
    assert banded == [((1, 0), (2, 0))]
    assert plain == [((0, 0), (1, 0))]


def test_closing_pairs_leaves_an_open_border_alone() -> None:
    tiles, owner = _strip()
    plain, _ = cross_pairs(tiles, owner, ())
    assert closing_pairs(plain, owner, {(0, 1)}) == [((1, 0), (2, 0))]

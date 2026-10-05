"""The flanks of a literal sprite: one tile beside each row on each side."""

from vcmi_mapgen.core.grid.flanks import closed_flanks, flank_tiles


def test_each_row_has_one_flank_tile_on_each_side() -> None:
    cells = [(3, 4), (4, 4), (5, 4), (4, 5)]
    assert flank_tiles(cells) == ([(2, 4), (3, 5)], [(6, 4), (5, 5)])


def test_one_closed_tile_closes_its_side() -> None:
    cells = [(3, 4), (3, 5)]
    assert closed_flanks(cells, lambda t: t == (2, 5)) == 1
    assert closed_flanks(cells, lambda t: t in {(2, 5), (4, 4)}) == 2
    assert closed_flanks(cells, lambda t: False) == 0

"""Tests for the BFS family over tile sets."""

from vcmi_mapgen.core.grid.reach import bfs8, entry_reach


def test_bfs8_crosses_a_diagonal_that_entry_reach_does_not() -> None:
    tiles = {(0, 0), (1, 1), (2, 1)}
    assert bfs8(tiles, (0, 0)) == tiles
    assert entry_reach(tiles, (0, 0)) == {(0, 0)}


def test_entry_reach_leaves_out_a_blocked_entry_but_spreads_past_it() -> None:
    assert entry_reach({(1, 0), (2, 0)}, (0, 0)) == {(1, 0), (2, 0)}
    assert entry_reach({(2, 0)}, (0, 0)) == set()
    assert entry_reach({(0, 0), (1, 0), (2, 0)}, (0, 0)) == {(0, 0), (1, 0), (2, 0)}

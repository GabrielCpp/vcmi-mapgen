"""Tests for the BFS family over tile sets."""

from vcmi_mapgen.core.grid.reach import STEPS8, distances, entry_reach, reach, walk


def test_reach8_crosses_a_diagonal_that_entry_reach_does_not() -> None:
    tiles = {(0, 0), (1, 1), (2, 1)}
    assert reach(tiles, [(0, 0)], STEPS8) == tiles
    assert entry_reach(tiles, (0, 0)) == {(0, 0)}


def test_entry_reach_leaves_out_a_blocked_entry_but_spreads_past_it() -> None:
    assert entry_reach({(1, 0), (2, 0)}, (0, 0)) == {(1, 0), (2, 0)}
    assert entry_reach({(2, 0)}, (0, 0)) == set()
    assert entry_reach({(0, 0), (1, 0), (2, 0)}, (0, 0)) == {(0, 0), (1, 0), (2, 0)}


def test_distances_count_steps_from_the_nearest_source() -> None:
    row = {(x, 0) for x in range(5)}
    assert distances(row, [(0, 0), (4, 0)]) == {
        (0, 0): 0,
        (4, 0): 0,
        (1, 0): 1,
        (3, 0): 1,
        (2, 0): 2,
    }


def test_walk_returns_the_goal_end_first_or_nothing() -> None:
    row = {(x, 0) for x in range(4)}
    assert walk([(0, 0)], {(3, 0)}, row) == [(3, 0), (2, 0), (1, 0), (0, 0)]
    assert walk([(0, 0)], {(9, 9)}, row) == []

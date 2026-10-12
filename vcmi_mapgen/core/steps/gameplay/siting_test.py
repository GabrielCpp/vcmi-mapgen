from typing import cast

import numpy as np

from vcmi_mapgen.core.steps.gameplay.siting import Codes, TileGrid, owner


def test_the_first_player_to_arrive_owns_a_tile() -> None:
    assert owner((7, 4)) == 1
    assert owner((4, 4)) == 0
    assert owner((None, None)) is None


def _worst(rows: list[str], r: int) -> list[str]:
    """Each tile of the one-level ASCII ``rows`` replaced by the worst code within ``r`` of it,
    a digit a tile with that code and ``.`` no tile."""
    cells = [(y, x, c) for y, row in enumerate(rows) for x, c in enumerate(row) if c != "."]
    grid = TileGrid(
        (1, len(rows), max(len(r) for r in rows)),
        (
            np.zeros(len(cells), dtype=np.intp),
            np.array([y for y, _x, _c in cells], dtype=np.intp),
            np.array([x for _y, x, _c in cells], dtype=np.intp),
        ),
    )
    values: Codes = np.array([int(c) for _y, _x, c in cells], dtype=np.int64)
    got = iter(cast(list[int], grid.worst_within(values, r).tolist()))
    return ["".join(c if c == "." else str(next(got)) for c in row) for row in rows]


def test_a_tile_takes_the_worst_code_within_reach() -> None:
    assert _worst(["000001"], 2) == ["000111"]


def test_the_worst_code_spreads_across_both_axes() -> None:
    assert _worst(["111", "111", "112"], 1) == ["111", "122", "122"]


def test_a_gap_in_the_grid_does_not_stop_the_reach() -> None:
    assert _worst(["0.3"], 2) == ["3.3"]


def test_two_levels_never_mix() -> None:
    grid = TileGrid(
        (2, 1, 1),
        (
            np.array([0, 1], dtype=np.intp),
            np.array([0, 0], dtype=np.intp),
            np.array([0, 0], dtype=np.intp),
        ),
    )
    assert grid.worst_within(np.array([0, 2]), 3).tolist() == [0, 2]

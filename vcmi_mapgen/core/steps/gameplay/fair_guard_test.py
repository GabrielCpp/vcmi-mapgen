from typing import cast

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.steps.gameplay.fair_guard import ARRIVALS, Codes, TileGrid, fair_guard


def _grid(rows: list[str]) -> tuple[TileGrid, Codes, NDArray[np.bool_]]:
    """A one-level grid from ASCII rows: a digit is a tile with that code, ``#`` a tile that
    does not count, ``.`` no tile."""
    cells = [(y, x, c) for y, row in enumerate(rows) for x, c in enumerate(row) if c != "."]
    shape = (1, len(rows), max(len(r) for r in rows))
    grid = TileGrid(
        shape,
        (
            np.zeros(len(cells), dtype=np.intp),
            np.array([y for y, _x, _c in cells], dtype=np.intp),
            np.array([x for _y, x, _c in cells], dtype=np.intp),
        ),
    )
    values = np.array([0 if c == "#" else int(c) for _y, _x, c in cells], dtype=np.int64)
    counted = np.array([c != "#" for _y, _x, c in cells], dtype=np.bool_)
    return grid, values, counted


def _rows(rows: list[str], got: Codes) -> list[str]:
    out = [list(r) for r in rows]
    it = iter(cast(list[int], got.tolist()))
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            if c != ".":
                out[y][x] = "#" if c == "#" else str(next(it))
    return ["".join(r) for r in out]


def _worst(rows: list[str], r: int) -> list[str]:
    grid, values, counted = _grid(rows)
    return _rows(rows, grid.worst_within(values, r, counted))


def test_a_tile_takes_the_worst_code_within_reach() -> None:
    assert _worst(["000001"], 2) == ["000111"]


def test_the_worst_code_spreads_across_both_axes() -> None:
    assert _worst(["111", "111", "112"], 1) == ["111", "122", "122"]


def test_a_tile_that_does_not_count_spreads_nothing() -> None:
    assert _worst(["00#00"], 2) == ["00#00"]


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
    got = grid.worst_within(np.array([0, 2]), 3, np.array([True, True]))
    assert got.tolist() == [0, 2]


def _guard(codes: list[list[int]], top: int) -> tuple[list[int], list[int]]:
    code, guard = fair_guard(lambda level: np.array(codes[level], dtype=np.int64), top, lambda c: c)
    return code.tolist(), guard.tolist()


def test_an_even_tile_takes_no_guard() -> None:
    assert _guard([[0, 1], [ARRIVALS, ARRIVALS]], 1) == ([0, 1], [0, 0])


def test_an_uneven_tile_takes_the_weakest_guard_that_evens_it() -> None:
    uneven = ARRIVALS
    assert _guard([[uneven], [uneven], [1], [0]], 3) == ([1], [2])


def test_no_guard_beyond_the_cap() -> None:
    uneven = ARRIVALS
    assert _guard([[uneven], [uneven], [0]], 1) == ([uneven], [0])


def test_a_tile_no_guard_evens_keeps_its_unguarded_code() -> None:
    assert _guard([[ARRIVALS + 1], [ARRIVALS * 2]], 1) == ([ARRIVALS + 1], [0])


def test_the_guard_is_judged_on_the_worst_code_nearby() -> None:
    grid, _values, counted = _grid(["00"])
    codes = [np.array([3, 0]), np.array([0, 3]), np.array([0, 0])]
    code, guard = fair_guard(
        lambda level: codes[level], 2, lambda c: grid.worst_within(c, 1, counted)
    )
    assert (code.tolist(), guard.tolist()) == ([0, 0], [2, 2])

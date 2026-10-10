"""The weakest guard that keeps the players' reach of a family even at each tile. A guard adds
the same toll for every player, so it moves an object into later bands, where the players
who reach it at all count it alike.

A tile's tier code is its spread change times ARRIVALS plus its arrival rank, so codes order
as the pair does and a code below ARRIVALS widens no gap."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

ARRIVALS = 3
FAIR_GUARD = 4

type Codes = NDArray[np.int64]


@dataclass(frozen=True, slots=True)
class TileGrid:
    """Where each ranked tile sits on a (levels, rows, columns) grid."""

    shape: tuple[int, int, int]
    cells: tuple[NDArray[np.intp], NDArray[np.intp], NDArray[np.intp]]

    def worst_within(self, values: Codes, r: int, counted: NDArray[np.bool_]) -> Codes:
        """Per tile, the largest of ``values`` within ``r`` tiles along its row, then along its
        column, over the ``counted`` tiles only."""
        low = np.iinfo(np.int64).min
        present = np.zeros(self.shape, dtype=np.bool_)
        present[self.cells] = counted
        grid = np.full(self.shape, low, dtype=np.int64)
        grid[self.cells] = values
        grid = np.where(present, grid, low)
        for axis in (2, 1):
            grid = np.where(present, _slide(grid, axis, r, low), low)
        return np.where(counted, grid[self.cells], values)


def _slide(a: Codes, axis: int, r: int, low: int) -> Codes:
    n = a.shape[axis]
    pad = [(0, 0)] * 3
    pad[axis] = (r, r)
    padded = np.pad(a, pad, constant_values=low)
    best = a.copy()
    for d in range(2 * r + 1):
        window = [slice(None)] * 3
        window[axis] = slice(d, d + n)
        _ = np.maximum(best, padded[tuple(window)], out=best)
    return best


def fair_guard(
    tier_at: Callable[[int], Codes],
    top: int,
    worst: Callable[[Codes], Codes],
) -> tuple[Codes, Codes]:
    """Per tile, the weakest guard level from 0 to ``top`` whose worst tier code nearby widens
    no gap, and that code. ``tier_at(level)`` gives each tile's code under a guard of that
    level and ``worst`` its worst code nearby. A tile no level evens keeps level 0 and its
    code there."""
    chosen = worst(tier_at(0))
    guard = np.zeros(len(chosen), dtype=np.int64)
    for level in range(1, top + 1):
        uneven = chosen >= ARRIVALS
        if not uneven.any():
            break
        code = worst(tier_at(level))
        take = uneven & (code < ARRIVALS)
        chosen = np.where(take, code, chosen)
        guard = np.where(take, level, guard)
    return chosen, guard

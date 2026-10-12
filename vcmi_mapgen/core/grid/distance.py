"""King's-move distance over a square map to the nearest of a set of tiles."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.model import Tile


def object_distance(size: int, cells: Sequence[Tile]) -> NDArray[np.int64]:
    """Per tile of a ``size`` square, the king's-move steps to the nearest of ``cells``,
    ``size`` where there is none."""
    far = np.full((size, size), size, dtype=np.int64)
    if not cells:
        return far
    seen = np.zeros((size, size), dtype=np.bool_)
    for x, y in cells:
        seen[y, x] = True
    far[seen] = 0
    for step in range(1, size):
        padded = np.pad(seen, 1)
        grown = np.zeros_like(seen)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                grown |= padded[1 + dy : 1 + dy + size, 1 + dx : 1 + dx + size]
        fresh = grown & ~seen
        if not fresh.any():
            break
        far[fresh] = step
        seen = grown
    return far

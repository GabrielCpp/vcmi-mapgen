# pyright: reportAny=false

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.jit import njit
from vcmi_mapgen.core.steps.vegetation.model import RINT

KW = 2 * RINT + 1
SAT = 2


@njit
def _pairwise_sum(a: NDArray[np.float64]) -> float:
    n = a.shape[0]
    if n < 8:
        res = 0.0
        for i in range(n):
            res += a[i]
        return res
    r = a[:8].copy()
    i = 8
    while i < n - n % 8:
        for j in range(8):
            r[j] += a[i + j]
        i += 8
    res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]))
    while i < n:
        res += a[i]
        i += 1
    return res


@njit
def energy(
    counts: NDArray[np.int16],
    theta: NDArray[np.float64],
    c: int,
    at: tuple[int, int],
    self_present: bool,
) -> float:
    """Geyer-saturated local interaction  sum_co,r theta[c][co][r] * min(n_co(r), SAT), over the
    padded count window [ly, ly+KW) x [lx, lx+KW) at `at` = (ly, lx)."""
    ly, lx = at
    cats = counts.shape[0]
    rings = RINT + 1
    terms = np.empty(cats * rings)
    ring_counts = np.empty(rings)
    for co in range(cats):
        ring_counts[:] = 0.0
        for dy in range(KW):
            for dx in range(KW):
                ring = max(abs(dx - RINT), abs(dy - RINT))
                ring_counts[ring] += counts[co, ly + dy, lx + dx]
        if self_present and co == c:
            ring_counts[0] -= 1.0
        for r in range(rings):
            terms[co * rings + r] = theta[c, co, r] * min(ring_counts[r], SAT)
    return _pairwise_sum(terms)

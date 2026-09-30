"""The cellular field that shapes a zone's vegetation before any object is placed.

A thresholded smooth Gaussian field percolates into one blob at corpus coverage. A cellular
(Worley) field does not: `F2 - F1`, the gap between a tile's nearest and second-nearest seed,
peaks around each seed and falls to zero on the Voronoi edges between them. Blocking the tiles
above a quantile leaves patches around the seeds and an open network along the edges. With
about one seed per 50 tiles, the pair correlation, patch count and patch size of the blocked
mask match held-out corpus zones.
"""

import random
from typing import cast

import numpy as np
from numpy.typing import NDArray

SEED_DENSITY = 0.02
PAD = 4
MAX_COVERAGE = 0.95


def cellular_field(
    w: int, h: int, rng: random.Random, density: float = SEED_DENSITY
) -> NDArray[np.float64]:
    """`F2 - F1` over a `w` x `h` box, from seeds drawn over the box padded by PAD so the
    edge tiles see the same seed density as the middle ones."""
    n = max(2, round(density * (w + 2 * PAD) * (h + 2 * PAD)))
    sx = np.array([rng.uniform(-PAD, w + PAD) for _ in range(n)])
    sy = np.array([rng.uniform(-PAD, h + PAD) for _ in range(n)])
    xx: NDArray[np.float64] = np.arange(w, dtype=np.float64)[None, :, None] + 0.5
    yy: NDArray[np.float64] = np.arange(h, dtype=np.float64)[:, None, None] + 0.5
    d = np.sort(np.hypot(xx - sx, yy - sy), axis=-1)
    jitter = np.array([rng.random() for _ in range(w * h)]).reshape(h, w)
    return cast(NDArray[np.float64], d[..., 1] - d[..., 0] + 1e-3 * jitter)


def coverage_by_ebin(
    profile: NDArray[np.float64], tiles_per_ebin: NDArray[np.int64], target: float
) -> NDArray[np.float64]:
    """Each edge bin's blocked share: the corpus `profile` of blocked mass by edge bin,
    scaled so the zone's mean over its `tiles_per_ebin` is `target`."""
    n = cast(int, tiles_per_ebin.sum())
    mean = cast(float, (profile * tiles_per_ebin).sum()) / n if n else 0.0
    if mean <= 0:
        return np.full(profile.shape, min(target, MAX_COVERAGE))
    return np.clip(target * profile / mean, 0.0, MAX_COVERAGE)


def target_mask(
    field: NDArray[np.float64],
    dom: NDArray[np.bool_],
    ebins: NDArray[np.int8],
    coverage: NDArray[np.float64],
    forced: NDArray[np.bool_],
) -> NDArray[np.bool_]:
    """The tiles to block: every `forced` tile of `dom`, and in each edge bin the free tiles
    whose `field` lies in the top `coverage[e]` share of that bin."""
    mask: NDArray[np.bool_] = forced & dom
    free: NDArray[np.bool_] = dom & ~forced
    for e, p in enumerate(cast(list[float], coverage.tolist())):
        sel = cast(NDArray[np.bool_], free & (ebins == e))
        if p > 0 and bool(sel.any()):
            cut = float(np.quantile(field[sel], 1 - p))
            mask = mask | (sel & (field > cut))
    return mask

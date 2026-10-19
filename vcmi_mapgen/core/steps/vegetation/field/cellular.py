"""The cellular field that shapes a zone's vegetation before any object is placed.

A thresholded smooth Gaussian field percolates into one blob at corpus coverage. A cellular
(Worley) field does not: `F2 - F1`, the gap between a tile's nearest and second-nearest seed,
peaks around each seed and falls to zero on the Voronoi edges between them. Blocking the
tiles below a quantile builds closed walls on the edges and leaves a room in each cell. The
seeds are blue noise, so the rooms come out of similar size. The walls are not complete: the
canvas refuses any placement that walls off open ground, so each room keeps at least one
opening.
"""

import math
import random
from typing import cast

import numpy as np
from numpy.typing import NDArray

SEED_DENSITY = 0.02
SPACING = 0.7
TRIES = 30
PAD = 4
MAX_COVERAGE = 0.95


def cellular_field(
    w: int, h: int, rng: random.Random, density: float = SEED_DENSITY
) -> NDArray[np.float64]:
    """`F2 - F1` over a `w` x `h` box, from blue-noise seeds drawn over the box padded by PAD so
    the edge tiles see the same seed density as the middle ones. Each seed lies `SPACING` mean
    spacings from every earlier one, and a seed that finds no spot in `TRIES` draws is dropped."""
    n = max(2, round(density * (w + 2 * PAD) * (h + 2 * PAD)))
    gap = SPACING * math.sqrt(1 / density)
    seeds: list[tuple[float, float]] = []
    for _ in range(n):
        for _ in range(TRIES):
            p = (rng.uniform(-PAD, w + PAD), rng.uniform(-PAD, h + PAD))
            if all(math.hypot(p[0] - q[0], p[1] - q[1]) >= gap for q in seeds):
                seeds.append(p)
                break
    while len(seeds) < 2:
        seeds.append((rng.uniform(-PAD, w + PAD), rng.uniform(-PAD, h + PAD)))
    sx = np.array([p[0] for p in seeds])
    sy = np.array([p[1] for p in seeds])
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
    whose `field` lies in the bottom `coverage[e]` share of that bin, the tiles nearest the
    Voronoi edges."""
    mask: NDArray[np.bool_] = forced & dom
    free: NDArray[np.bool_] = dom & ~forced
    for e, p in enumerate(cast(list[float], coverage.tolist())):
        sel = cast(NDArray[np.bool_], free & (ebins == e))
        if p > 0 and bool(sel.any()):
            cut = float(np.quantile(field[sel], p))
            mask = mask | (sel & (field < cut))
    return mask

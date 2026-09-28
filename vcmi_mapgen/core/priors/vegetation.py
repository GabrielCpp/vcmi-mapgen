"""The corpus vegetation prior: per-terrain decoration statistics and the fits the
vegetation sampler reads from them."""

import math
from dataclasses import dataclass

RMAX = 6  # pair-correlation rings 0..RMAX (Chebyshev)


@dataclass(frozen=True, slots=True)
class CellStats:
    size: int
    n: int
    sum: int
    sum2: int


@dataclass(slots=True)
class VegetationStats:
    terrain: str
    nzones: int
    tiles: int
    nanchors: int
    tiles_per_ebin: list[int]
    anch: dict[str, list[int]]
    lam: dict[str, list[float]]
    lam_tot: dict[str, float]
    g: dict[str, list[float]]
    pairN: dict[str, list[int]]
    pairD: list[int]
    anim_w: dict[str, dict[str, int]]
    mean_blk_cells: dict[str, float]
    cell: CellStats | None
    veg_blocked_frac: float
    runs: dict[str, float]


def theta(
    stats: VegetationStats, min_pairs: int = 30, lo: float = -1.5, hi: float = 2.0
) -> dict[str, list[float]]:
    """Pairwise log-potentials  theta[a][b][r] = clip(log ghat_ab(r))  (spec §2.6 counting fit).
    Rings with fewer than `min_pairs` observed pairs are neutral (0) — too sparse to trust."""
    th: dict[str, list[float]] = {}
    for key, gr in stats.g.items():
        N = stats.pairN[key]
        th[key] = [
            max(lo, min(hi, math.log(gr[r]))) if N[r] >= min_pairs and gr[r] > 0 else 0.0
            for r in range(RMAX + 1)
        ]
    return th


def theta_local(
    stats: VegetationStats,
    rint: int = 2,
    base_r: int = 4,
    min_pairs: int = 30,
    clip: tuple[float, float] = (-1.5, 1.5),
) -> dict[str, list[float]]:
    """LOCAL pair potentials, background-normalized:  theta[a][b][r] = log(g(r) / g(base_r)),
    r <= rint. The raw g(r) > 1 at ALL ranges because zones mix dense forest masses with
    clearings (large-scale inhomogeneity); fitting that as pair attraction makes the Gibbs
    process explosive. Dividing by the mid-range g isolates the genuinely LOCAL clumping /
    stacking excess; the large-scale part is carried by the Cox log-field (`cox_sigma`)."""
    lo, hi = clip
    th: dict[str, list[float]] = {}
    for key, gr in stats.g.items():
        N = stats.pairN[key]
        base = gr[base_r] if (N[base_r] >= min_pairs and gr[base_r] > 0) else None
        row: list[float] = []
        for r in range(rint + 1):
            if base and N[r] >= min_pairs and gr[r] > 0:
                row.append(max(lo, min(hi, math.log(gr[r] / base))))
            else:
                row.append(0.0)
        th[key] = row
    return th


def cox_sigma(stats: VegetationStats) -> float:
    """Log-field std of the Cox modulation, fitted from coarse-cell overdispersion: for a
    log-Gaussian Cox process the Fisher index of cell counts is  F = 1 + m(e^{s^2}-1)  with
    m the mean count, so  s^2 = ln(1 + (F-1)/m)  (Møller & Waagepetersen 2004, ch. 5)."""
    c = stats.cell
    if c is None or c.n < 10 or c.sum <= 0:
        return 0.0
    m = c.sum / c.n
    var = c.sum2 / c.n - m * m
    F = var / m
    return math.sqrt(max(0.0, math.log(1.0 + max(0.0, F - 1.0) / m)))

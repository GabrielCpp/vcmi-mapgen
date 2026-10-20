"""Fit the spacing law of each kind of copy: the normalised nearest-copy distance u of every
spaced object on the corpus maps, pooled over sizes and levels."""

import math
from collections import defaultdict
from collections.abc import Callable, Sequence

import numpy as np
from numpy.typing import NDArray
from scipy import stats

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.priors.spacing import (
    EXPONENTIAL,
    GAMMA,
    KDE,
    LOGNORMAL,
    MIN_SAMPLES,
    WEIBULL,
    SpacingFit,
    SpacingPriors,
)
from vcmi_mapgen.core.reading.repeats import copy_spacing, kind_key

FLOOR = 1e-9
ALPHA = 0.01
KDE_POINTS = 200

type Params = tuple[float, ...]
type Floats = NDArray[np.float64]
type Fitted = tuple[Params, float, stats.rv_continuous, Params]


def _exponential(v: Floats) -> Fitted:
    _loc, scale = stats.expon.fit(v, floc=0)
    s = float(scale)
    return (s,), float(np.sum(stats.expon.logpdf(v, 0, s))), stats.expon, (0.0, s)


def _weibull(v: Floats) -> Fitted:
    shape, _loc, scale = stats.weibull_min.fit(v, floc=0)
    k, s = float(shape), float(scale)
    return (
        (k, s),
        float(np.sum(stats.weibull_min.logpdf(v, k, 0, s))),
        stats.weibull_min,
        (k, 0.0, s),
    )


def _gamma(v: Floats) -> Fitted:
    shape, _loc, scale = stats.gamma.fit(v, floc=0)
    a, s = float(shape), float(scale)
    return (a, s), float(np.sum(stats.gamma.logpdf(v, a, 0, s))), stats.gamma, (a, 0.0, s)


def _lognormal(v: Floats) -> Fitted:
    shape, _loc, scale = stats.lognorm.fit(v, floc=0)
    sigma, s = float(shape), float(scale)
    ll = float(np.sum(stats.lognorm.logpdf(v, sigma, 0, s)))
    return (sigma, math.log(s)), ll, stats.lognorm, (sigma, 0.0, s)


FAMILY_FITS: dict[str, Callable[[Floats], Fitted]] = {
    EXPONENTIAL: _exponential,
    WEIBULL: _weibull,
    GAMMA: _gamma,
    LOGNORMAL: _lognormal,
}


def _quantiles(v: Floats, qs: Sequence[float]) -> list[float]:
    return [float(np.quantile(v, q)) for q in qs]


def chi_square_p(v: Floats, dist: stats.rv_continuous, args: Params, free: int) -> float | None:
    """The chi-square p-value of ``v`` against ``dist`` in equal-probability bins, None when
    there are fewer than two samples per bin."""
    n = len(v)
    k = min(max(n // 10, 5), 20)
    if n < 2 * k:
        return None
    edges = np.asarray(dist.ppf(np.linspace(0, 1, k + 1)[1:-1], *args), dtype=np.float64)
    observed = np.bincount(np.searchsorted(edges, v), minlength=k).astype(np.float64)
    stat = float(np.sum((observed - n / k) ** 2 / (n / k)))
    return float(stats.chi2.sf(stat, max(k - 1 - free, 1)))


def fit_samples(samples: Sequence[float]) -> SpacingFit:
    """The law of ``samples``: the parametric family of lowest AIC, kept unless its chi-square
    p-value is under ``ALPHA``, when a reflected Gaussian kernel density over 200 empirical
    quantiles takes its place."""
    v = np.maximum(np.array(sorted(samples), dtype=float), FLOOR)
    n = len(v)
    best: tuple[float, str, Params, stats.rv_continuous, Params] | None = None
    for family, fitter in FAMILY_FITS.items():
        params, ll, dist, args = fitter(v)
        aic = 2 * len(params) - 2 * ll
        if best is None or aic < best[0]:
            best = (aic, family, params, dist, args)
    assert best is not None
    aic, family, params, dist, args = best
    p10, p50, p90 = _quantiles(v, (0.1, 0.5, 0.9))
    p = chi_square_p(v, dist, args, len(params))
    if p is None or p >= ALPHA:
        return SpacingFit(family, params, n, p10, p50, p90, aic, p if p is not None else 0.0)
    points = tuple(_quantiles(v, [i / (KDE_POINTS - 1) for i in range(KDE_POINTS)]))
    q1, q3 = _quantiles(v, (0.25, 0.75))
    spread = min(float(np.std(v)), (q3 - q1) / 1.34)
    bandwidth = max(0.9 * spread * math.pow(n, -0.2), FLOOR)
    return SpacingFit(KDE, (bandwidth,), n, p10, p50, p90, aic, p, points)


def mine_spacing(catalog: Catalog, maps: Sequence[MapState]) -> SpacingPriors:
    """Per kind with at least ``MIN_SAMPLES`` copies, and per purpose over all its copies, the
    fitted law of u over every corpus map."""
    by_kind: defaultdict[str, list[float]] = defaultdict(list)
    by_purpose: defaultdict[str, list[float]] = defaultdict(list)
    for state in maps:
        for kind, purpose, u in copy_spacing(catalog, state):
            by_kind[kind_key(kind)].append(u)
            by_purpose[purpose].append(u)
    return SpacingPriors(
        kinds={k: fit_samples(u) for k, u in sorted(by_kind.items()) if len(u) >= MIN_SAMPLES},
        pools={p: fit_samples(u) for p, u in sorted(by_purpose.items()) if len(u) >= 2},
    )

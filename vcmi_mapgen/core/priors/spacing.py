"""The spacing prior: how far a copy of a kind stands from its nearest copy, as the normalised
distance u = n * pi * x^2 / land. Random placement gives u an exponential law of scale 1."""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import cast

import numpy as np
from numpy.typing import NDArray

MIN_SAMPLES = 30
EXPONENTIAL = "exponential"
WEIBULL = "weibull"
GAMMA = "gamma"
LOGNORMAL = "lognormal"
KDE = "kde"
FAMILIES = (EXPONENTIAL, WEIBULL, GAMMA, LOGNORMAL, KDE)

type Floats = NDArray[np.float64]
type Flags = NDArray[np.bool_]


def baseline(u: float) -> float:
    """The density of u under random placement: the exponential of scale 1."""
    return math.exp(-u) if u >= 0 else 0.0


@dataclass(frozen=True, slots=True)
class SpacingFit:
    """One fitted law of u: its ``family``, the ``params`` of that family with location fixed
    at zero (scale for exponential, shape and scale for weibull and gamma, sigma and mu of
    log u for lognormal, the bandwidth for kde), the sample count ``n``, the empirical
    quantiles ``p10``, ``p50`` and ``p90`` it was fitted on, the ``aic`` and the chi-square
    p-value ``chi_p`` of the best parametric family, and for kde the 200 evenly spaced
    empirical quantiles in ``samples``."""

    family: str
    params: tuple[float, ...]
    n: int
    p10: float
    p50: float
    p90: float
    aic: float
    chi_p: float
    samples: tuple[float, ...] = ()

    def density(self, u: float) -> float:
        """The probability density of u under this fit, zero below zero."""
        return cast(float, self.density_of(np.array([u], dtype=np.float64)).tolist()[0])

    def density_of(self, u: Floats) -> Floats:
        """The probability density of each u under this fit, zero below zero."""
        pos: Floats = np.maximum(u, 0.0)
        out = self._positive(pos, np.equal(pos, 0))
        return np.where(np.less(u, 0), 0.0, out)

    def _positive(self, pos: Floats, zero: Flags) -> Floats:
        safe: Floats = np.where(zero, 1.0, pos)
        if self.family == EXPONENTIAL:
            scale = self.params[0]
            return np.exp(-pos / scale) / scale
        if self.family == WEIBULL:
            k, scale = self.params
            z: Floats = safe / scale
            out: Floats = k / scale * np.power(z, k - 1) * np.exp(-np.power(z, k))
            return np.where(zero, 1 / scale if k == 1 else (math.inf if k < 1 else 0.0), out)
        if self.family == GAMMA:
            a, scale = self.params
            logs: Floats = (
                (a - 1) * np.log(safe) - safe / scale - math.lgamma(a) - a * math.log(scale)
            )
            return np.where(
                zero, 1 / scale if a == 1 else (math.inf if a < 1 else 0.0), np.exp(logs)
            )
        if self.family == LOGNORMAL:
            sigma, mu = self.params
            z = (np.log(safe) - mu) / sigma
            return np.where(
                zero, 0.0, np.exp(-0.5 * z * z) / math.sqrt(2 * math.pi) / (safe * sigma)
            )
        if self.family == KDE:
            h = self.params[0]
            samples = np.array(self.samples, dtype=np.float64)
            gap: Floats = (pos[:, None] - samples[None, :]) / h
            mirror: Floats = (pos[:, None] + samples[None, :]) / h
            both = cast(Floats, np.exp(-0.5 * gap * gap) + np.exp(-0.5 * mirror * mirror))
            total = cast(Floats, np.sum(both, axis=1))
            return total / math.sqrt(2 * math.pi) / (len(self.samples) * h)
        raise ValueError(f"unknown spacing family {self.family}")


@dataclass(frozen=True, slots=True)
class SpacingPriors:
    """The spacing fit of each kind with at least ``MIN_SAMPLES`` samples, keyed by
    ``repeats.kind_key``, and one pooled fit per purpose."""

    kinds: Mapping[str, SpacingFit] = field(default_factory=dict[str, SpacingFit])
    pools: Mapping[str, SpacingFit] = field(default_factory=dict[str, SpacingFit])

    def fit_for(self, key: str, purpose: str) -> SpacingFit | None:
        """The kind's own fit, else its purpose's pool, else None."""
        return self.kinds.get(key) or self.pools.get(purpose)

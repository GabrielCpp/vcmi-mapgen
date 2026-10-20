"""The spacing prior: how far a copy of a kind stands from its nearest copy, as the normalised
distance u = n * pi * x^2 / land. Random placement gives u an exponential law of scale 1."""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

MIN_SAMPLES = 30
EXPONENTIAL = "exponential"
WEIBULL = "weibull"
GAMMA = "gamma"
LOGNORMAL = "lognormal"
KDE = "kde"
FAMILIES = (EXPONENTIAL, WEIBULL, GAMMA, LOGNORMAL, KDE)


def baseline(u: float) -> float:
    """The density of u under random placement: the exponential of scale 1."""
    return math.exp(-u) if u >= 0 else 0.0


def _normal_pdf(z: float) -> float:
    return math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)


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
        if u < 0:
            return 0.0
        if self.family == EXPONENTIAL:
            scale = self.params[0]
            return math.exp(-u / scale) / scale
        if self.family == WEIBULL:
            k, scale = self.params
            if u == 0:
                return 1 / scale if k == 1 else (math.inf if k < 1 else 0.0)
            z = u / scale
            return k / scale * math.pow(z, k - 1) * math.exp(-math.pow(z, k))
        if self.family == GAMMA:
            a, scale = self.params
            if u == 0:
                return 1 / scale if a == 1 else (math.inf if a < 1 else 0.0)
            return math.exp(
                (a - 1) * math.log(u) - u / scale - math.lgamma(a) - a * math.log(scale)
            )
        if self.family == LOGNORMAL:
            sigma, mu = self.params
            if u == 0:
                return 0.0
            return _normal_pdf((math.log(u) - mu) / sigma) / (u * sigma)
        if self.family == KDE:
            h = self.params[0]
            total = sum(_normal_pdf((u - s) / h) + _normal_pdf((u + s) / h) for s in self.samples)
            return total / (len(self.samples) * h)
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

import math
from typing import cast

import numpy as np
from scipy import stats

from vcmi_mapgen.core.priors.spacing import SpacingFit, SpacingPriors, baseline


def _fit(family: str, params: tuple[float, ...], samples: tuple[float, ...] = ()) -> SpacingFit:
    return SpacingFit(family, params, 100, 0.1, 0.7, 2.0, 0.0, 0.5, samples)


def test_each_parametric_density_matches_scipy() -> None:
    for u in (0.05, 0.5, 1.7, 4.0):
        assert math.isclose(
            _fit("exponential", (1.3,)).density(u), stats.expon.pdf(u, 0, 1.3), rel_tol=1e-9
        )
        assert math.isclose(
            _fit("weibull", (1.4, 0.9)).density(u),
            stats.weibull_min.pdf(u, 1.4, 0, 0.9),
            rel_tol=1e-9,
        )
        assert math.isclose(
            _fit("gamma", (2.2, 0.6)).density(u), stats.gamma.pdf(u, 2.2, 0, 0.6), rel_tol=1e-9
        )
        assert math.isclose(
            _fit("lognormal", (0.7, -0.2)).density(u),
            stats.lognorm.pdf(u, 0.7, 0, math.exp(-0.2)),
            rel_tol=1e-9,
        )


def test_the_array_density_matches_the_scalar_one_of_each_family() -> None:
    us = np.array([-0.3, 0.0, 0.05, 0.5, 1.7, 4.0])
    samples = tuple(i / 50 for i in range(1, 100))
    fits = (
        _fit("exponential", (1.3,)),
        _fit("weibull", (1.4, 0.9)),
        _fit("gamma", (2.2, 0.6)),
        _fit("lognormal", (0.7, -0.2)),
        _fit("kde", (0.3,), samples),
    )
    for fit in fits:
        got = fit.density_of(us)
        assert got[0] == 0.0
        for u, g in zip(
            cast(list[float], us.tolist()), cast(list[float], got.tolist()), strict=True
        ):
            if u >= 0:
                assert math.isclose(fit.density(u), g, rel_tol=1e-12, abs_tol=1e-12)
    assert np.allclose(fits[1].density_of(us[2:]), stats.weibull_min.pdf(us[2:], 1.4, 0, 0.9))
    assert np.allclose(fits[2].density_of(us[2:]), stats.gamma.pdf(us[2:], 2.2, 0, 0.6))


def test_a_negative_u_has_no_density() -> None:
    assert _fit("exponential", (1.0,)).density(-0.1) == 0.0
    assert baseline(0.0) == 1.0
    assert math.isclose(baseline(1.0), math.exp(-1))


def test_the_reflected_kde_integrates_to_one() -> None:
    samples = tuple(i / 100 for i in range(1, 200))
    fit = _fit("kde", (0.3,), samples)
    steps = 4000
    h = 20 / steps
    total = sum((fit.density(i * h) + fit.density((i + 1) * h)) * h / 2 for i in range(steps))
    assert math.isclose(total, 1.0, abs_tol=0.01)


def test_a_kind_without_a_fit_falls_back_to_its_purpose_pool() -> None:
    own, pool = _fit("exponential", (1.0,)), _fit("exponential", (2.0,))
    priors = SpacingPriors({"a:b": own}, {"MANA": pool})
    assert priors.fit_for("a:b", "MANA") == own
    assert priors.fit_for("c:d", "MANA") == pool
    assert priors.fit_for("c:d", "MINE") is None

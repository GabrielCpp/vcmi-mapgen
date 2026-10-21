import math
from typing import cast

import numpy as np

from vcmi_mapgen.core.priors.spacing import SpacingFit, SpacingPriors
from vcmi_mapgen.core.steps.gameplay.spacing import FLOOR, SpotWeight

KIND = ("windmill", None)
KEY = "windmill:"


def _fit(family: str, params: tuple[float, ...]) -> SpacingFit:
    return SpacingFit(family, params, 100, 0.3, 1.4, 3.0, 0.0, 0.5)


def _weights(
    fit: SpacingFit, spots: list[tuple[int, int, int]], copies: list[tuple[int, int, int]]
) -> list[float]:
    spread = SpotWeight(SpacingPriors({KEY: fit}), {KIND: 20}, {0: 10000, 1: 10000})
    weight, _crowded = spread.spots(KIND, "BONUS", np.array(spots, dtype=np.int64), copies)
    return cast(list[float], weight.tolist())


def test_the_weight_prefers_the_best_distance_of_the_law_over_a_copy_beside() -> None:
    best = math.sqrt(2.0 * 10000 / (10 * math.pi))
    beside, at_best = _weights(
        _fit("gamma", (3.0, 0.5)), [(0, 51, 50), (0, 50 + round(best), 50)], [(0, 50, 50)]
    )
    assert math.isclose(beside, FLOOR, abs_tol=1e-3)
    assert at_best > 0.95


def test_the_weight_stays_between_the_floor_and_one() -> None:
    spots = [(0, x, 50) for x in range(51, 150)]
    got = _weights(_fit("gamma", (3.0, 0.5)), spots, [(0, 50, 50)])
    assert min(got) >= FLOOR - 1e-12
    assert math.isclose(max(got), 1.0, abs_tol=0.02)


def test_a_spot_far_from_every_copy_takes_the_weight_at_the_cap() -> None:
    far, other_level, near_cap = _weights(
        _fit("gamma", (3.0, 0.5)), [(0, 5000, 50), (1, 50, 50), (0, 50, 50)], [(0, 40, 40)]
    )
    assert far == other_level
    assert far > FLOOR
    assert near_cap < far


def test_a_random_law_weighs_every_spot_the_same() -> None:
    got = _weights(
        _fit("exponential", (1.0,)), [(0, 51, 50), (0, 90, 50), (1, 5, 5)], [(0, 50, 50)]
    )
    assert all(math.isclose(w, 1.0, abs_tol=1e-9) for w in got)


def test_a_kind_with_one_copy_or_no_fit_weighs_one() -> None:
    lone = SpotWeight(SpacingPriors({KEY: _fit("gamma", (3.0, 0.5))}), {KIND: 1}, {0: 10000})
    bare = SpotWeight(SpacingPriors(), {KIND: 10}, {0: 10000})
    at = np.array([(0, 51, 50)], dtype=np.int64)
    for spread in (lone, bare):
        weight, crowded = spread.spots(KIND, "BONUS", at, [(0, 50, 50)])
        assert weight.tolist() == [1.0]
        assert crowded.tolist() == [False]


def test_a_spot_beside_a_copy_is_crowded_and_a_far_one_is_not() -> None:
    spread = SpotWeight(SpacingPriors({KEY: _fit("gamma", (3.0, 0.5))}), {KIND: 20}, {0: 10000})
    at = np.array([(0, 51, 50), (0, 90, 50), (0, 5000, 50)], dtype=np.int64)
    _weight, crowded = spread.spots(KIND, "BONUS", at, [(0, 50, 50)])
    assert crowded.tolist() == [True, False, False]

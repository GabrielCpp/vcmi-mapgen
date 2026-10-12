import math
import random

import pytest

from vcmi_mapgen.corpus.mine.counts import fit_count, fit_stretch


def _maps(rng: random.Random, n: int) -> list[int]:
    return [rng.choice([1000, 2000, 4000, 8000, 16000]) for _ in range(n)]


def _draw(rng: random.Random, mu: float) -> int:
    return sum(rng.random() < mu / 1000 for _ in range(1000))


def test_fit_count_recovers_the_land_exponent_of_a_synthetic_corpus() -> None:
    rng = random.Random(7)
    land = _maps(rng, 400)
    counts = [_draw(rng, math.exp(-5.0) * math.pow(x, 0.8)) for x in land]
    curve = fit_count(land, counts)
    assert curve.land_exp == pytest.approx(0.8, abs=0.05)
    assert curve.players_exp == 0.0
    assert curve.expected(4000, 2) == curve.expected(4000, 8)
    assert curve.expected(4000, 4) == pytest.approx(math.exp(-5.0) * 4000**0.8, rel=0.1)


def test_the_cap_pins_a_land_exponent_the_corpus_overshoots() -> None:
    rng = random.Random(3)
    land = _maps(rng, 300)
    counts = [_draw(rng, math.exp(-9.0) * math.pow(x, 1.3)) for x in land]
    curve = fit_count(land, counts, cap=1.0)
    assert curve.land_exp == 1.0
    assert curve.expected(4000, 2) > 0


def test_fit_stretch_recovers_the_slope_of_the_days() -> None:
    rng = random.Random(5)
    land = [rng.choice([1000, 4000, 16000]) for _ in range(600)]
    days = [round(math.expm1(0.3 * math.log(x) + 0.5 + rng.gauss(0, 0.2))) for x in land]
    assert fit_stretch(land, days) == pytest.approx(0.3, abs=0.05)

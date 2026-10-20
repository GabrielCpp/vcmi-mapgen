import random

from vcmi_mapgen.corpus.mine.spacing import fit_samples


def test_exponential_samples_fit_a_law_with_the_same_median() -> None:
    rng = random.Random(7)
    samples = [rng.expovariate(1.0) for _ in range(600)]
    fit = fit_samples(samples)
    assert fit.n == 600
    assert abs(fit.p50 - 0.693) < 0.1
    assert fit.family != "kde"
    assert fit.density(0.5) > 0.0

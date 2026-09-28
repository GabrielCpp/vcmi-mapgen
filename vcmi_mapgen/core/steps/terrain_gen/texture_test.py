import collections
import random

from vcmi_mapgen.core.steps.terrain_gen.texture import border_band, sample


def test_sample_draws_only_keys_with_counts() -> None:
    rng = random.Random(1)
    counter = collections.Counter({4: 3, 7: 0})
    assert {sample(counter, rng) for _ in range(20)} == {4}


def test_border_band_covers_band_around_a_terrain_change() -> None:
    grid = [[1] * 5 + [2] * 5 for _ in range(3)]
    band = border_band(grid)
    assert all(band[y][x] for y in range(3) for x in range(2, 8))
    assert not any(band[y][0] or band[y][9] for y in range(3))

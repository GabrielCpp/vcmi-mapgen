"""Tests for choosing the home places on the grown shapes."""

import math
import random

from vcmi_mapgen.core.steps.terrain_gen.homes import choose_homes, home_points
from vcmi_mapgen.core.steps.terrain_gen.layout import Layout


def _strips(n: int, width: int, side: int) -> Layout:
    label = [[min(x // width, n - 1) for x in range(side)] for _ in range(side)]
    anchors = tuple((p * width + width // 2, side // 2) for p in range(n))
    return Layout(label, anchors, n)


def test_a_home_fits_only_a_place_with_the_tiles_a_town_needs() -> None:
    layout = _strips(4, 15, 60)
    assert sorted(home_points(layout)) == [0, 1, 2, 3]
    assert not home_points(_strips(30, 2, 60))


def test_the_homes_stand_apart_and_share_no_neighbour() -> None:
    layout = _strips(6, 12, 72)
    for seed in range(5):
        homes = choose_homes(layout, 2, (0.5, math.inf), random.Random(seed))
        assert len(homes.places) == 2
        assert homes.crowded == 0
        assert homes.gap >= 0.5


def test_too_few_roomy_places_fall_back_on_any_place() -> None:
    layout = _strips(3, 4, 12)
    homes = choose_homes(layout, 2, (0.0, math.inf), random.Random(0))
    assert len(homes.places) == 2


def test_a_home_stands_in_a_place_no_larger_than_the_budget_when_enough_fit() -> None:
    label = [[0 if x < 30 else 1 if x < 45 else 2 if x < 60 else 3 for x in range(72)]] * 72
    layout = Layout(label, ((15, 36), (37, 36), (52, 36), (66, 36)), 4)
    for seed in range(5):
        homes = choose_homes(layout, 2, (0.0, 15 * 72), random.Random(seed))
        assert 0 not in homes.places
    homes = choose_homes(layout, 2, (0.0, 12 * 72), random.Random(0))
    assert len(homes.places) == 2

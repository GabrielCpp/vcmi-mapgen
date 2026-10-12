import numpy as np

from vcmi_mapgen.core.steps.compensation.prize import deficits, prize_ground, prize_tier

BAR = {20: 0.5, 40: 0.4}


def test_a_player_at_the_bar_lacks_nothing() -> None:
    assert deficits({20: (100, 50), 40: (100, 40)}, BAR) == (0, 0)


def test_the_deficit_is_the_gap_to_the_bar_at_the_worse_horizon() -> None:
    assert deficits({20: (10000, 2000), 40: (20000, 7000)}, BAR) == (0, 3000)


def test_the_prize_is_the_cheapest_tier_that_covers_the_deficit() -> None:
    assert prize_tier(0) is None
    assert prize_tier(1500) == "treasure"
    assert prize_tier(4000) == "minor"
    assert prize_tier(10000) == "major"
    assert prize_tier(90000) == "relic"


def test_the_ground_holds_the_tiles_the_player_reaches_strictly_first_in_time() -> None:
    totals = np.array([[3, 5, 5, 30, -1], [4, 9, 5, 40, 2]], dtype=np.int64)
    assert prize_ground(totals, 0, 20).tolist() == [True, True, False, False, False]
    assert prize_ground(totals, 1, 20).tolist() == [False, False, False, False, True]


def test_a_tile_no_rival_reaches_belongs_to_the_player_who_does() -> None:
    totals = np.array([[6], [-1]], dtype=np.int64)
    assert prize_ground(totals, 0, 20).tolist() == [True]

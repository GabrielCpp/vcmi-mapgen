from vcmi_mapgen.core.steps.gameplay.reach import Reach


def test_an_object_counts_in_its_band_and_every_band_after() -> None:
    reach = Reach(2)
    reach.add("bank", (2, None))
    assert reach.within("bank", 0) == [0, 1, 1, 1]
    assert reach.within("bank", 1) == [0, 0, 0, 0]


def test_one_object_ahead_costs_nothing_within_the_slack() -> None:
    reach = Reach(2)
    assert reach.cost("bank", (1, None), 1) == 0


def test_a_second_object_ahead_spreads_every_band_it_reaches() -> None:
    reach = Reach(2)
    reach.add("bank", (1, None))
    assert reach.cost("bank", (3, None), 1) == 2


def test_an_object_both_players_reach_keeps_them_even() -> None:
    reach = Reach(2)
    reach.add("bank", (1, None))
    assert reach.cost("bank", (1, 1), 1) == 0


def test_families_count_apart() -> None:
    reach = Reach(2)
    reach.add("bank", (1, None))
    assert reach.cost("shrine", (4, None), 0) == 1


def test_a_single_player_never_spreads() -> None:
    reach = Reach(1)
    reach.add("bank", (1,))
    assert reach.cost("bank", (1,), 0) == 0


def test_an_added_object_clears_the_cached_cost() -> None:
    reach = Reach(2)
    assert reach.cost("bank", (1, None), 0) == 4
    reach.add("bank", (None, 1))
    assert reach.cost("bank", (1, None), 0) == -4


def test_an_object_that_narrows_a_gap_costs_below_zero() -> None:
    reach = Reach(2)
    for _ in range(3):
        reach.add("bank", (1, None))
    assert reach.cost("bank", (None, 1), 0) == -4

import numpy as np

from vcmi_mapgen.core.steps.gameplay.gold import GoldSpot


def test_gold_stands_past_the_far_floor_on_contested_land() -> None:
    spot = GoldSpot([(0, 1)])
    days = np.array([[5, 7], [9, 10], [9, 20], [12, 12], [-1, -1]], dtype=np.int64)
    ok, key = spot.rank(days)
    assert ok.tolist() == [False, True, False, True, False]
    assert key[ok].tolist() == [1, 0]


def test_gold_without_an_enemy_ranks_the_farthest_first() -> None:
    ok, key = GoldSpot([]).rank(np.array([[9, 12], [15, -1], [4, 30]], dtype=np.int64))
    assert ok.tolist() == [True, True, False]
    assert key[ok].tolist() == [-9, -15]


def test_one_spot_reads_the_same_rule() -> None:
    spot = GoldSpot([(0, 1)])
    assert spot.admits([10, 12])
    assert not spot.admits([10, None])
    assert not spot.admits([8, 9])


def test_the_loose_rule_admits_the_far_spots_the_strict_one_leaves_out() -> None:
    days = np.array([[5, 20], [9, 10], [9, 20], [9, -1]], dtype=np.int64)
    ok, _key = GoldSpot([(0, 1)]).rank(days, loose=True)
    assert ok.tolist() == [False, False, True, True]
    loose, _key = GoldSpot([]).rank(days, loose=True)
    assert not loose.any()


def test_the_mine_guard_counts_toward_the_far_floor() -> None:
    days = np.array([[5, 6]], dtype=np.int64)
    assert not GoldSpot([(0, 1)]).rank(days)[0].item(0)
    assert GoldSpot.of([(0, 1)], (0, 3, 5, 8, 12, 18, 28, 45)).rank(days)[0].item(0)


def test_a_close_spot_takes_the_lowest_guard_that_passes_the_far_floor() -> None:
    walk = np.array([[2, 9], [7, 9], [12, 14], [-1, -1], [0, 0]], dtype=np.int64)
    toll = (0, 3, 5, 8)
    days = np.stack([np.where(walk >= 0, walk + t, -1) for t in toll])
    assert GoldSpot([(0, 1)]).guards(days, 1, 3).tolist() == [3, 1, 1, -1, -1]
    assert GoldSpot([(0, 1)]).guards(days, 0, 2).tolist() == [-1, 1, 0, -1, -1]


def test_a_guard_no_stronger_than_the_way_in_adds_no_days() -> None:
    days = np.array([[[6, 9]], [[6, 9]], [[7, 9]], [[10, 12]]], dtype=np.int64)
    assert GoldSpot([(0, 1)]).guards(days, 1, 3).tolist() == [3]

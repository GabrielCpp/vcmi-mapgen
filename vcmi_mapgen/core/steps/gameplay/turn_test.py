import random
from collections import Counter

from vcmi_mapgen.core.steps.gameplay.bands import BandPlan, Slot
from vcmi_mapgen.core.steps.gameplay.turn import (
    Stop,
    Turn,
    fill,
    near,
    nearest_first,
    rare_slots,
    resource_turn,
)


def _band(d: int) -> int:
    return 1 if d < 5 else 2 if d < 10 else 3 if d < 15 else 4


def test_a_family_not_met_yet_comes_first() -> None:
    assert resource_turn({"a": 2, "b": 1}, {"a": 1}, 2, []) == "b"


def test_a_standing_mine_ahead_holds_its_share() -> None:
    assert resource_turn({"a": 1, "b": 1}, {}, 1, [(10, "a")]) == "b"
    assert resource_turn({"a": 1}, {}, 1, [(5, "a")]) is None


def test_the_family_whose_standing_mine_comes_last_goes_first() -> None:
    assert resource_turn({"a": 2, "b": 2}, {}, 1, [(5, "a"), (9, "b")]) == "b"


def test_fill_keeps_what_each_player_holds() -> None:
    assert fill([1, 0], 3, 0) == [2, 1]
    assert fill([1, 0], 3, 1) == [1, 2]
    assert fill([2, 0], 2, 0) == [2, 0]


def test_the_counts_hold_with_standing_mines_ahead_on_a_way() -> None:
    plan = BandPlan({f: [1] * 20 for f in "abc"}, _band, 2, random.Random(1))
    quota = {"a": 2, "b": 2, "c": 2}
    slots = rare_slots(plan, quota, {"a": [(0, 9)], "b": [(0, 10)]}, {})
    assert Counter(s.family for s in slots) == {"a": 1, "b": 1, "c": 2}
    assert {s.family for s in slots if s.player == 0} == {"c"}


def test_near_holds_the_players_within_slack_of_the_first() -> None:
    assert near([5, 6, None, 9]) == ((0, 5), (1, 6))


def test_the_turn_takes_the_family_that_repeats_on_no_way() -> None:
    turn = Turn(Counter({"a": 1, "b": 1}), {"a": 0, "b": 0}, (0,), 1)
    held = Stop("a", ((0, 3),), 0, (10, 10))
    at = Stop("a", ((0, 5),), 0, (30, 30))
    assert turn.order(at, [held]) == [("b", True), ("a", False)]


def test_the_turn_takes_a_family_with_no_mine_close_by() -> None:
    turn = Turn(Counter({"a": 1, "b": 2}), {"a": 0, "b": 0}, (0,), 2)
    held = Stop("a", ((1, 3),), 0, (10, 10))
    at = Stop("a", ((0, 5),), 0, (12, 10))
    assert turn.order(at, [held]) == [("b", True), ("a", False)]


def test_nearest_first_orders_the_families_by_target_in_their_places() -> None:
    other, far, close = Slot("x"), Slot("a", 0, 2, 9), Slot("b", 1, 1, 3)
    assert nearest_first([other, far, close], {"a", "b"}) == [other, close, far]

import random

from vcmi_mapgen.core.planning.content import PlaceIntent
from vcmi_mapgen.core.planning.zone_index import ZoneRecord
from vcmi_mapgen.core.steps.loot import pocket_plan as PP


def test_a_small_or_flat_pocket_is_shallow() -> None:
    assert PP.pocket_kind(1, 1) is PP.PocketKind.SHALLOW
    assert PP.pocket_kind(2, 2) is PP.PocketKind.SHALLOW
    assert PP.pocket_kind(4, 1) is PP.PocketKind.SHALLOW


def test_a_big_and_deep_pocket_is_deep() -> None:
    assert PP.pocket_kind(3, 2) is PP.PocketKind.DEEP
    assert PP.pocket_kind(12, 5) is PP.PocketKind.DEEP


def test_a_richer_ward_takes_a_stronger_guard() -> None:
    assert PP.guard_level_for_value(750) == 1
    assert PP.guard_level_for_value(2750) == 2
    assert PP.guard_level_for_value(10000) == 4
    assert PP.guard_level_for_value(40000) == 6


def test_the_ward_tier_follows_the_place_guard_mean() -> None:
    rng = random.Random(4)
    assert {PP.ward_tier(rng, 1.0) for _ in range(20)} == {"treasure"}
    assert {PP.ward_tier(rng, 7.0) for _ in range(20)} == {"relic"}


def test_largest_takes_the_first_of_the_biggest() -> None:
    small = ((0, 0), frozenset({(1, 0)}), frozenset({(0, 0)}))
    big = ((5, 5), frozenset({(6, 5), (7, 5)}), frozenset({(5, 5)}))
    twin = ((9, 9), frozenset({(8, 9), (7, 9)}), frozenset({(9, 9)}))
    assert PP.largest([small, big, twin]) == big


def test_the_deepest_spots_are_the_farthest_from_the_mouth() -> None:
    spots = [(1, 0), (2, 0), (3, 0), (4, 0)]
    assert PP.deepest_spots(spots, (0, 0), 2) == [(3, 0), (4, 0)]
    assert PP.deepest_spots(spots, (0, 0), 0) == []


def test_the_level_plan_reads_each_planned_zone_guard_mean() -> None:
    ts_a = frozenset((x, y) for x in range(10) for y in range(10))
    ts_b = frozenset((x, y) for x in range(10, 20) for y in range(10))
    records = [
        ZoneRecord(0, "grass", ts_a, ts_a, ts_a),
        ZoneRecord(1, "grass", ts_b, ts_b, ts_b),
        ZoneRecord(2, "grass", frozenset(), frozenset(), frozenset()),
    ]
    intents = {
        0: PlaceIntent("middle", 1, 1.0, 3.0),
        1: PlaceIntent("treasure", 2, 1.0, 5.0),
    }
    assert PP.level_plan(intents, records) == PP.PocketPlan({0: 3.0, 1: 5.0})


def test_a_level_without_intents_has_no_plan() -> None:
    ts = frozenset({(0, 0)})
    assert PP.level_plan({}, [ZoneRecord(0, "grass", ts, ts, ts)]) is None

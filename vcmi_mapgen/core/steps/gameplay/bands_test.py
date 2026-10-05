import random

from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.reading.families import mine_family
from vcmi_mapgen.core.steps.gameplay.bands import (
    BandPlan,
    Slot,
    band_sequence,
    band_shares,
    player_split,
    slot_order,
)
from vcmi_mapgen.core.steps.gameplay.quota import RANKS


def _band(d: int) -> int:
    return 1 if d < 5 else 2 if d < 10 else 3 if d < 15 else 4


def test_the_remainder_goes_to_the_players_from_start() -> None:
    assert player_split(5, 2, 0) == [3, 2]
    assert player_split(5, 2, 1) == [2, 3]


def test_band_shares_follow_the_corpus_days() -> None:
    days = [1] * 5 + [3] * 5
    assert band_shares(days, _band) == [0.25, 0.75, 0.0, 0.0]


def test_no_corpus_days_put_every_object_in_the_first_band() -> None:
    assert band_shares([], _band) == [1.0, 0.0, 0.0, 0.0]


def test_every_prefix_of_the_sequence_follows_the_shares() -> None:
    seq = band_sequence([0.5, 0.5, 0.0, 0.0], 6)
    for k in range(2, 7, 2):
        assert seq[:k].count(1) == seq[:k].count(2)


def test_each_player_gets_the_same_bands_within_one() -> None:
    plan = BandPlan({"bank": [1] * 10 + [1] * 10}, _band, 2, random.Random(1))
    slots = plan.slots("bank", 7, [], 0)
    for b in range(1, 5):
        per = [sum(1 for s in slots if s.player == p and s.band == b) for p in range(2)]
        assert max(per) - min(per) <= 1


def test_each_target_lies_inside_its_band() -> None:
    plan = BandPlan({"bank": [2] * 20}, _band, 2, random.Random(1))
    for s in plan.slots("bank", 8, [], 0):
        assert s.band is not None and s.target is not None
        assert _band(s.target) == s.band


def test_a_standing_object_takes_its_players_slot() -> None:
    plan = BandPlan({"bank": [1] * 5}, _band, 2, random.Random(1))
    slots = plan.slots("bank", 4, [(0, 1)], 0)
    assert [s.player for s in slots].count(0) == 1


def test_a_map_without_players_gets_bare_slots() -> None:
    plan = BandPlan({}, _band, 0, random.Random(1))
    assert plan.slots("bank", 3, [None], 0) == [Slot("bank")] * 2


def test_mines_go_before_banks_and_far_bands_first() -> None:
    ore = mine_family("ore")
    slots = [Slot(Purpose.BANK, 0, 1), Slot(ore, 0, 1), Slot(ore, 0, 3)]
    order = slot_order(slots, RANKS)
    assert [(s.family, s.band) for s in order] == [(ore, 3), (ore, 1), (Purpose.BANK, 1)]

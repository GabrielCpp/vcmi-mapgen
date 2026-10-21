import random

from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.priors.effort import BANDS
from vcmi_mapgen.core.reading.families import FAR_DAYS, mine_family
from vcmi_mapgen.core.steps.gameplay.bands import (
    BandPlan,
    Slot,
    band_sequence,
    band_shares,
    slot_order,
    stretched,
)
from vcmi_mapgen.core.steps.gameplay.quota import RANKS


def _band(d: int) -> int:
    return 1 if d < 5 else 2 if d < 10 else 3 if d < 15 else 4


def test_band_shares_follow_the_corpus_days() -> None:
    days = [1] * 5 + [3] * 5
    assert band_shares(days, _band) == [0.25, 0.75] + [0.0] * (BANDS - 2)


def test_no_corpus_days_put_every_object_in_the_first_band() -> None:
    assert band_shares([], _band) == [1.0] + [0.0] * (BANDS - 1)


def test_every_prefix_of_the_sequence_follows_the_shares() -> None:
    seq = band_sequence([0.5, 0.5, 0.0, 0.0], 6)
    for k in range(2, 7, 2):
        assert seq[:k].count(1) == seq[:k].count(2)


def test_shared_slots_serve_no_player_and_split_over_the_bands() -> None:
    plan = BandPlan({"bank": [1] * 5 + [1] * 5}, _band, 2, random.Random(1))
    slots = plan.shared("bank", 6, [])
    assert {s.player for s in slots} == {None}
    assert sorted(s.band or 0 for s in slots) == [1, 1, 1, 2, 2, 2]


def test_each_target_lies_inside_its_band() -> None:
    plan = BandPlan({"bank": [2] * 20}, _band, 2, random.Random(1))
    for s in plan.shared("bank", 8, []):
        assert s.band is not None and s.target is not None
        assert _band(s.target) == s.band


def test_a_standing_object_takes_the_nearest_band_left() -> None:
    plan = BandPlan({"bank": [1] * 5}, _band, 2, random.Random(1))
    assert [s.band for s in plan.shared("bank", 3, [3])] == [1, 1]


def test_a_standing_object_no_player_reaches_takes_the_furthest_band_left() -> None:
    plan = BandPlan({"bank": [1] * 5 + [1] * 5}, _band, 2, random.Random(1))
    assert [s.band for s in plan.shared("bank", 4, [None])] == [1, 1, 2]


def test_a_map_without_players_gets_bare_slots() -> None:
    plan = BandPlan({}, _band, 0, random.Random(1))
    assert plan.shared("bank", 3, [None]) == [Slot("bank")] * 2


def test_mines_go_before_banks_and_far_bands_first() -> None:
    ore = mine_family("ore")
    slots = [Slot(Purpose.BANK, 0, 1), Slot(ore, 0, 1), Slot(ore, 0, 3)]
    order = slot_order(slots, RANKS)
    assert [(s.family, s.band) for s in order] == [(ore, 3), (ore, 1), (Purpose.BANK, 1)]


def test_a_unit_factor_leaves_the_corpus_days_in_place() -> None:
    days = [0, 2, 5, 1]
    assert stretched(days, 1.0)[: len(days)] == tuple(days)


def test_a_stretch_moves_each_day_out_by_the_factor() -> None:
    out = stretched([0, 0, 4, 0, 1], 2.0)
    assert (out[4], out[8], sum(out)) == (4, 1, 5)


def test_a_stretch_never_passes_the_far_day() -> None:
    out = stretched([0] * FAR_DAYS + [3], 3.0)
    assert (out[FAR_DAYS], sum(out)) == (3, 3)

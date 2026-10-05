import random

from vcmi_mapgen.core.model import Footprint, Identity, Role
from vcmi_mapgen.core.model.artifact import ArtifactSet, ArtifactTier
from vcmi_mapgen.core.placement.prizes import HeldPrize
from vcmi_mapgen.core.steps.sets.deal import (
    Dealer,
    deal_one,
    deal_sets,
    set_quota,
    share,
    top_slots,
)
from vcmi_mapgen.core.steps.sets.slots import NO_HOME, Slot

ART = Identity("artifact", "x", "ava0001", Footprint.one(Role.VISIT))


def _slot(x: int, band: int, effort: int, home: int) -> Slot:
    return Slot(HeldPrize(0, (x, 0), "grass", ART), band, effort, home)


def test_one_set_per_72_square_counting_both_levels() -> None:
    assert set_quota(1, 36) == 1
    assert set_quota(1, 72) == 1
    assert set_quota(2, 72) == 2
    assert set_quota(2, 144) == 8


def test_only_reached_slots_of_the_top_two_bands_take_parts() -> None:
    slots = [_slot(0, 4, 50, 0), _slot(1, 3, 20, 1), _slot(2, 2, 10, 0), _slot(3, 4, 0, NO_HOME)]
    assert [s.held.tile for s in top_slots(slots)] == [(0, 0), (1, 0)]


def test_share_deals_round_robin_over_homes_costliest_first() -> None:
    slots = [_slot(0, 4, 40, 0), _slot(1, 4, 30, 0), _slot(2, 4, 35, 1), _slot(3, 4, 10, 1)]
    picks = share(slots, 3)
    assert picks is not None
    assert [s.held.tile for s in picks] == [(0, 0), (2, 0), (1, 0)]
    assert share(slots, 5) is None


def test_the_best_part_goes_to_the_costliest_slot() -> None:
    tiers: dict[str, ArtifactTier] = {"a": "treasure", "b": "relic", "c": "major"}
    picks = [_slot(0, 3, 15, 0), _slot(1, 4, 40, 1), _slot(2, 4, 25, 0)]
    deal = deal_one(ArtifactSet("abc", ("a", "b", "c")), picks, tiers)
    assert [(s.held.tile, p) for s, p in deal.parts] == [
        ((1, 0), "b"),
        ((2, 0), "c"),
        ((0, 0), "a"),
    ]


def test_deals_stop_at_the_quota_and_use_each_slot_once() -> None:
    sets = [ArtifactSet("pair", ("p", "q")), ArtifactSet("trio", ("r", "s", "t"))]
    slots = [_slot(x, 4, 40 - x, x % 2) for x in range(6)]
    deals = deal_sets(Dealer(sets, {}, 2), slots, random.Random(1))
    assert sorted(d.name for d in deals) == ["pair", "trio"]
    used = [s.held.tile for d in deals for s, _ in d.parts]
    assert len(used) == len(set(used)) == 5


def test_no_set_is_dealt_when_too_few_slots_fit_it() -> None:
    sets = [ArtifactSet("trio", ("r", "s", "t"))]
    slots = [_slot(0, 4, 40, 0), _slot(1, 4, 30, 1), _slot(2, 2, 5, 0)]
    assert deal_sets(Dealer(sets, {}, 1), slots, random.Random(1)) == []

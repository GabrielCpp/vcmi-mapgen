import random

from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.priors.counts import MINE_CURVE, TOWN_CURVE, CountCurve
from vcmi_mapgen.core.priors.gameplay import TerrainStats
from vcmi_mapgen.core.reading.families import mine_family
from vcmi_mapgen.core.reading.mines import MapMeasure
from vcmi_mapgen.core.steps.gameplay.quota import (
    CurveRule,
    Group,
    MapCount,
    RateRule,
    family_quota,
    group_rules,
    paired,
    split,
)

ORE, WOOD, MILL = mine_family("orePit"), mine_family("sawmill"), mine_family("windmill")
GEMS, SULFUR = mine_family("gemPond"), mine_family("sulfurDune")


def _stats(tiles: int, counts: dict[str, int]) -> TerrainStats:
    return TerrainStats(tiles, counts, {}, {}, {}, {}, [], [], [], 0.0, {})


def test_the_rate_rule_follows_the_corpus_rate_per_tile() -> None:
    st = _stats(100, {Purpose.BANK: 5})
    assert RateRule([(200, st), (200, st)], Purpose.BANK).expected() == 20


def test_the_curve_rule_reads_the_curve_at_the_map_measure() -> None:
    curve = CountCurve(0.0, 0.5, 1.0)
    assert CurveRule(curve, MapMeasure(400, 2)).expected() == 40


def test_the_density_multiplier_scales_every_count() -> None:
    st = _stats(100, {Purpose.BANK: 10})
    groups = [Group((Purpose.BANK,), RateRule([(100, st)], Purpose.BANK))]
    assert family_quota(groups, {}, 0.5, 0, random.Random(1))[Purpose.BANK] == 5


def test_standing_towns_count_inside_the_town_quota() -> None:
    st = _stats(100, {Purpose.TOWN: 3})
    groups = [Group((Purpose.TOWN,), RateRule([(100, st)], Purpose.TOWN))]
    assert family_quota(groups, {}, 1.0, 2, random.Random(1))[Purpose.TOWN] == 1


def test_split_gives_the_remainder_to_the_largest_fractions() -> None:
    assert split(5, {"a": 1.0, "b": 1.0, "c": 2.0}) == {"a": 1, "b": 1, "c": 3}


def test_split_shares_evenly_when_every_weight_is_zero() -> None:
    assert split(4, {"a": 0.0, "b": 0.0}) == {"a": 2, "b": 2}


def test_resource_mines_follow_the_curve_and_split_by_corpus_count() -> None:
    corpus = {GEMS: [3, 3], SULFUR: [1, 1]}
    count = MapCount([], MapMeasure(64, 1), ["gemPond", "sulfurDune"], corpus)
    groups = group_rules(CountCurve(0.0, 0.5, 0.0), TOWN_CURVE, count)
    quota = family_quota(groups, corpus, 1.0, 0, random.Random(1))
    assert (quota[GEMS], quota[SULFUR]) == (6, 2)


def test_the_town_pair_stays_out_of_the_mine_quota() -> None:
    corpus = {ORE: [3], WOOD: [3], GEMS: [3]}
    count = MapCount([], MapMeasure(64, 1), ["orePit", "sawmill", "gemPond"], corpus)
    groups = group_rules(CountCurve(0.0, 0.5, 0.0), TOWN_CURVE, count)
    quota = family_quota(groups, corpus, 1.0, 0, random.Random(1))
    assert (ORE in quota, WOOD in quota, quota[GEMS]) == (False, False, 8)


def test_each_town_takes_its_pair_off_the_mine_quota() -> None:
    groups = [Group((GEMS,), CurveRule(CountCurve(0.0, 0.5, 0.0), MapMeasure(64, 1)), 2)]
    assert family_quota(groups, {}, 1.0, 3, random.Random(1))[GEMS] == 2


def test_the_paired_families_are_the_ones_towns_take_off() -> None:
    corpus = {ORE: [3], GEMS: [3], MILL: [1]}
    count = MapCount([], MapMeasure(64, 1), ["orePit", "gemPond", "windmill"], corpus)
    assert paired(group_rules(MINE_CURVE, TOWN_CURVE, count)) == {GEMS}


def test_producers_take_the_mine_rate_times_their_corpus_share() -> None:
    st = _stats(100, {Purpose.MINE: 10})
    corpus = {GEMS: [3], MILL: [1]}
    count = MapCount([(200, st)], MapMeasure(200, 2), ["gemPond", "windmill"], corpus)
    groups = group_rules(MINE_CURVE, TOWN_CURVE, count)
    assert [g.families for g in groups[1:3]] == [(GEMS,), (MILL,)]
    assert groups[2].rule.expected() == 5


def test_towns_follow_the_town_curve() -> None:
    count = MapCount([], MapMeasure(400, 2), [], {})
    groups = group_rules(MINE_CURVE, CountCurve(0.0, 0.5, 1.0), count)
    assert groups[0].rule.expected() == 40

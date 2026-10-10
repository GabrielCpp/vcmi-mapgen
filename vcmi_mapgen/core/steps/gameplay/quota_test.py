import random

from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.priors.gameplay import TerrainStats
from vcmi_mapgen.core.priors.mines import MineCurve
from vcmi_mapgen.core.reading.families import mine_family
from vcmi_mapgen.core.reading.mines import MapMeasure
from vcmi_mapgen.core.steps.gameplay.quota import (
    CurveRule,
    Group,
    MapCount,
    RateRule,
    family_quota,
    group_rules,
    split,
)

ORE, WOOD, MILL = mine_family("orePit"), mine_family("sawmill"), mine_family("windmill")


def _stats(tiles: int, counts: dict[str, int]) -> TerrainStats:
    return TerrainStats(tiles, counts, {}, {}, {}, {}, [], [], [], 0.0, {})


def test_the_rate_rule_follows_the_corpus_rate_per_tile() -> None:
    st = _stats(100, {Purpose.BANK: 5})
    assert RateRule([(200, st), (200, st)], Purpose.BANK).expected() == 20


def test_the_curve_rule_reads_the_curve_at_the_map_measure() -> None:
    curve = MineCurve(0.0, 0.5, 1.0)
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
    corpus = {ORE: [3, 3], WOOD: [1, 1]}
    count = MapCount([], MapMeasure(64, 1), ["orePit", "sawmill"], corpus)
    groups = group_rules(MineCurve(0.0, 0.5, 0.0), count)
    quota = family_quota(groups, corpus, 1.0, 0, random.Random(1))
    assert (quota[ORE], quota[WOOD]) == (6, 2)


def test_producers_take_the_mine_rate_times_their_corpus_share() -> None:
    st = _stats(100, {Purpose.MINE: 10})
    corpus = {ORE: [3], MILL: [1]}
    count = MapCount([(200, st)], MapMeasure(200, 2), ["orePit", "windmill"], corpus)
    groups = group_rules(MineCurve(), count)
    assert [g.families for g in groups[1:3]] == [(ORE,), (MILL,)]
    assert groups[2].rule.expected() == 5

import random

from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.priors.gameplay import TerrainStats
from vcmi_mapgen.core.reading.families import mine_family
from vcmi_mapgen.core.steps.gameplay.quota import family_quota, purpose_quota, split


def _stats(tiles: int, counts: dict[str, int]) -> TerrainStats:
    return TerrainStats(tiles, counts, {}, {}, {}, {}, [], [], [], 0.0, {})


def test_the_quota_follows_the_corpus_rate_per_tile() -> None:
    st = _stats(100, {Purpose.MINE: 5})
    quota = purpose_quota([(200, st), (200, st)], 1.0, 0, random.Random(1))
    assert quota[Purpose.MINE] == 20


def test_the_density_multiplier_scales_the_quota() -> None:
    st = _stats(100, {Purpose.BANK: 10})
    assert purpose_quota([(100, st)], 0.5, 0, random.Random(1))[Purpose.BANK] == 5


def test_standing_towns_count_inside_the_town_quota() -> None:
    st = _stats(100, {Purpose.TOWN: 3})
    assert purpose_quota([(100, st)], 1.0, 2, random.Random(1))[Purpose.TOWN] == 1


def test_split_gives_the_remainder_to_the_largest_fractions() -> None:
    assert split(5, {"a": 1.0, "b": 1.0, "c": 2.0}) == {"a": 1, "b": 1, "c": 3}


def test_split_shares_evenly_when_every_weight_is_zero() -> None:
    assert split(4, {"a": 0.0, "b": 0.0}) == {"a": 2, "b": 2}


def test_mines_split_by_the_corpus_count_of_each_resource() -> None:
    corpus = {mine_family("ore"): [3, 3], mine_family("wood"): [1, 1]}
    quota = family_quota({Purpose.MINE: 8}, ["ore", "wood"], corpus)
    assert quota == {mine_family("ore"): 6, mine_family("wood"): 2}

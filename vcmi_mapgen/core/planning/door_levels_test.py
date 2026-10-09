import random

from vcmi_mapgen.core.planning.door_levels import DEFAULT_DOOR_LEVEL, DoorSpread, spread_level
from vcmi_mapgen.core.priors.territories import TerritoryStats

SPREAD = DoorSpread(player=(2, 2), neutral=(0, 6, 9))


def test_a_level_draws_all_its_doors_from_one_corpus_map() -> None:
    stats = TerritoryStats(player_doors_by_map=((1, 1), (5, 5)), neutral_doors_by_map=((3,),))
    spread = DoorSpread.draw(stats, random.Random(4))
    assert spread.player in ((1, 1), (5, 5))
    assert spread.neutral == (3,)


def test_a_corpus_without_doors_draws_an_empty_spread() -> None:
    assert DoorSpread.draw(TerritoryStats(), random.Random(1)) == DoorSpread()


def test_a_player_crossing_draws_from_the_player_doors() -> None:
    assert spread_level(SPREAD, True, random.Random(1)) == 2


def test_a_neutral_crossing_draws_a_level_from_1_to_7() -> None:
    assert spread_level(SPREAD, False, random.Random(1)) == 6


def test_an_empty_spread_falls_back_to_the_default_level_within_the_cap() -> None:
    assert spread_level(DoorSpread(), True, random.Random(1)) == DEFAULT_DOOR_LEVEL
    assert spread_level(DoorSpread(), True, random.Random(1), cap=2) == 2

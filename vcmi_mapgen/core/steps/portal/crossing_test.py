import random

from vcmi_mapgen.core.planning.door_levels import DoorSpread
from vcmi_mapgen.core.steps.portal.crossing import Side, may_join, pair_guard_level, side_of
from vcmi_mapgen.core.steps.terrain_gen.result import TerritoryPlan

PLAN = TerritoryPlan(zones={1: 0, 2: 1, 3: 2, 4: 2}, owners=(0, 1, None))
SPREAD = DoorSpread(player=(6,), neutral=(2,))


def test_a_zone_takes_the_side_of_its_territory() -> None:
    assert side_of(PLAN, 1) == Side(0, 0)
    assert side_of(PLAN, 4) == Side(2, None)
    assert side_of(PLAN, 9) == Side()


def test_a_portal_never_joins_two_player_territories() -> None:
    assert not may_join(side_of(PLAN, 1), side_of(PLAN, 2))
    assert may_join(side_of(PLAN, 1), side_of(PLAN, 3))
    assert may_join(side_of(PLAN, 3), side_of(PLAN, 4))


def test_a_pair_inside_one_territory_keeps_the_prize_level() -> None:
    ends = (side_of(PLAN, 3), side_of(PLAN, 4))
    assert pair_guard_level(SPREAD, ends, 4, random.Random(1)) == 4


def test_a_pair_out_of_a_player_territory_draws_from_the_player_doors() -> None:
    ends = (side_of(PLAN, 3), side_of(PLAN, 1))
    assert pair_guard_level(SPREAD, ends, 4, random.Random(1)) == 6


def test_a_pair_between_neutral_territories_draws_from_the_neutral_doors() -> None:
    ends = (Side(2, None), Side(5, None))
    assert pair_guard_level(SPREAD, ends, 4, random.Random(1)) == 2

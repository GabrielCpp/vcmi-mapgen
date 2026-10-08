"""Tests for core.steps.terrain_gen.territories (the territories of a place map)."""

import random

import pytest

from vcmi_mapgen.core.model import Entrance
from vcmi_mapgen.core.planning.entrances import Passages
from vcmi_mapgen.core.reading.borders import AdjacencyKind
from vcmi_mapgen.core.steps.terrain_gen import territories as TR
from vcmi_mapgen.core.steps.terrain_gen.result import PlannedDoor, TerritoryPlan

CLOSED, GATED, OPEN = AdjacencyKind.CLOSED, AdjacencyKind.GATED, AdjacencyKind.OPEN

CHAIN = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)]


def test_draw_count_ignores_zero_and_falls_back_to_one() -> None:
    assert TR.draw_count([0, 0, 3], random.Random(1)) == 3
    assert TR.draw_count([0], random.Random(1)) == 1
    assert TR.draw_count([], random.Random(1)) == 1


def test_group_neutral_grows_connected_groups_to_their_drawn_size() -> None:
    groups = TR.group_neutral(range(6), CHAIN, [2], random.Random(4))
    assert sorted(p for g in groups for p in g) == list(range(6))
    assert all(len(g) == 2 for g in groups)
    for g in groups:
        assert tuple(sorted(g)) in CHAIN


def test_group_neutral_stops_where_no_free_neighbour_is_left() -> None:
    assert TR.group_neutral([0, 1, 2], [(0, 1)], [5], random.Random(0)) == [[0, 1], [2]]


def test_draw_partition_gives_each_home_its_neighbours_and_groups_the_rest() -> None:
    owners = [0, None, None, None, None, 1]
    territory = TR.draw_partition(owners, CHAIN, [2], [3], random.Random(2))
    assert territory[0] == territory[1] == 0
    assert territory[5] == territory[4] == 1
    assert territory[2] == territory[3] == 2


def test_draw_partition_clamps_a_home_to_the_neighbours_it_has() -> None:
    territory = TR.draw_partition([0, None], [(0, 1)], [9], [1], random.Random(0))
    assert territory == (0, 0)


def test_draw_partition_refuses_two_homes_sharing_a_neighbour() -> None:
    with pytest.raises(ValueError, match="shares a neighbour"):
        _ = TR.draw_partition([0, None, 1], [(0, 1), (1, 2)], [2], [1], random.Random(0))


def test_settle_splits_a_territory_the_growth_cut_in_two() -> None:
    territory, lords = TR.settle([0, 0, 0, 1], [3, None, None, None], [(0, 1), (2, 3)])
    assert territory == (0, 0, 1, 2)
    assert lords == (3, None, None)
    territory, lords = TR.settle([0, 0, 0, 1], [None, None, 3, None], [(0, 1), (1, 3)])
    assert territory == (0, 0, 1, 2)
    assert lords == (None, 3, None)


def test_draw_doors_opens_a_spanning_forest_of_the_territories() -> None:
    territory = [0, 0, 1, 1, 2]
    realised = [(0, 2), (1, 3), (3, 4), (0, 1), (2, 3)]
    doors = TR.draw_doors(territory, realised, [(1, 3), (3, 4)], [1], random.Random(0))
    assert doors == {(1, 3): 1, (3, 4): 1}


def test_draw_doors_puts_a_second_door_on_another_pair_or_the_same_one() -> None:
    territory = [0, 0, 1, 1]
    realised = [(0, 2), (1, 3)]
    doors = TR.draw_doors(territory, realised, [(0, 2)], [2], random.Random(0))
    assert doors == {(0, 2): 1, (1, 3): 1}
    doors = TR.draw_doors([0, 1], [(0, 1)], [], [5], random.Random(0))
    assert doors == {(0, 1): 2}


def test_wall_kinds_keeps_inner_kinds_gates_doors_and_walls_the_rest() -> None:
    territory = [0, 0, 1, 1]
    realised = [(0, 1), (0, 2), (1, 3), (2, 3)]
    inner = {(0, 1): OPEN, (2, 3): CLOSED}
    kinds = TR.wall_kinds(territory, realised, inner, [(0, 2)])
    assert kinds == {(0, 1): OPEN, (0, 2): GATED, (1, 3): CLOSED, (2, 3): CLOSED}


def test_territory_plan_publishes_one_door_per_crossing() -> None:
    passages = Passages(
        {
            0: [Entrance((1, 0), frozenset({(1, 0)}), 1), Entrance((1, 5), frozenset(), 1)],
            1: [Entrance((2, 0), frozenset({(2, 0)}), 0), Entrance((2, 5), frozenset(), 0)],
        }
    )
    plan = TR.territory_plan([0, 1], [None, 4], {(0, 1): 2}, passages)
    assert plan.zones == {0: 0, 1: 1}
    assert plan.owners == (None, 4)
    assert plan.doors == (
        PlannedDoor((0, 1), (0, 1), (None, 4), ((1, 0), (2, 0))),
        PlannedDoor((0, 1), (0, 1), (None, 4), ((1, 5), (2, 5))),
    )
    assert plan.zones_of(1) == (1,)


def test_a_door_names_its_player_side() -> None:
    door = PlannedDoor((2, 5), (1, 3), (None, 0), ((0, 0), (1, 0)))
    assert door.player_side() == 5
    assert PlannedDoor((2, 5), (1, 3), (None, None), ((0, 0), (1, 0))).player_side() is None


def test_stranded_names_the_players_no_door_opens() -> None:
    door = PlannedDoor((0, 1), (0, 1), (0, None), ((0, 0), (1, 0)))
    plan = TerritoryPlan({0: 0, 1: 1, 2: 2}, (0, None, 1), (door,))
    assert TR.stranded(plan) == [1]
    assert TR.stranded(TerritoryPlan({0: 0}, (0,), ())) == []

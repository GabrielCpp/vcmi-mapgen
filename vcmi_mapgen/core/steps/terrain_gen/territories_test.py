"""Tests for core.steps.terrain_gen.territories (the territories of a place map)."""

import random

import pytest

from vcmi_mapgen.core.model import Entrance
from vcmi_mapgen.core.planning.entrances import Passages
from vcmi_mapgen.core.priors.territories import TerritoryCount
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
    territory = TR.draw_partition(owners, CHAIN, [2], 3, random.Random(2))
    assert territory[0] == territory[1] == 0
    assert territory[5] == territory[4] == 1
    assert territory[2] == territory[3] == 2


def test_draw_partition_clamps_a_home_to_the_neighbours_it_has() -> None:
    territory = TR.draw_partition([0, None], [(0, 1)], [9], 1, random.Random(0))
    assert territory == (0, 0)


def test_draw_partition_refuses_two_homes_sharing_a_neighbour() -> None:
    with pytest.raises(ValueError, match="shares a neighbour"):
        _ = TR.draw_partition([0, None, 1], [(0, 1), (1, 2)], [2], 3, random.Random(0))


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
    doors = TR.draw_doors(territory, (realised, [(1, 3), (3, 4)]), [1], random.Random(0))
    assert doors == {(1, 3): 1, (3, 4): 1}


def test_draw_doors_puts_a_second_door_on_another_pair_or_the_same_one() -> None:
    territory = [0, 0, 1, 1]
    realised = [(0, 2), (1, 3)]
    doors = TR.draw_doors(territory, (realised, [(0, 2)]), [2], random.Random(0))
    assert doors == {(0, 2): 1, (1, 3): 1}
    doors = TR.draw_doors([0, 1], ([(0, 1)], []), [5], random.Random(0))
    assert doors == {(0, 1): 2}


RING = {(0, 1): [(0, 1)], (1, 2): [(1, 2)], (2, 3): [(2, 3)], (0, 3): [(0, 3), (0, 7)]}
PATH = [(0, 1), (1, 2), (2, 3)]


def test_detour_doors_joins_a_touching_pair_too_many_doors_apart() -> None:
    added = TR.detour_doors(RING, PATH, TR.MAX_HOP, random.Random(0))
    assert len(added) == 1
    assert next(iter(added)) in RING[(0, 3)]
    assert TR.detour_doors(RING, PATH, 3, random.Random(0)) == {}


def test_detour_doors_joins_every_far_pair_and_every_cut_off_pair() -> None:
    chain = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)]
    choices = {tp: [tp] for tp in [*chain, (0, 3), (2, 5), (5, 6)]}
    added = TR.detour_doors(choices, chain, TR.MAX_HOP, random.Random(0))
    assert added == {(0, 3): 1, (2, 5): 1, (5, 6): 1}


def test_detour_doors_draws_the_same_doors_from_the_same_seed() -> None:
    first = TR.detour_doors(RING, PATH, TR.MAX_HOP, random.Random(5))
    assert first == TR.detour_doors(RING, PATH, TR.MAX_HOP, random.Random(5))


def test_draw_doors_puts_a_detour_door_on_a_planned_zone_pair() -> None:
    territory = [0, 1, 2, 3, 3]
    realised = [(0, 1), (1, 2), (2, 3), (0, 4), (0, 3)]
    planned = [(0, 1), (1, 2), (2, 3), (0, 4)]
    for seed in range(8):
        doors = TR.draw_doors(territory, (realised, planned), [1], random.Random(seed))
        assert set(doors) <= set(planned)
        assert (0, 4) in doors or (2, 3) in doors


def test_draw_doors_closes_every_ring_of_four_territories() -> None:
    ring = [(0, 1), (1, 2), (2, 3), (0, 3)]
    for seed in range(8):
        doors = TR.draw_doors([0, 1, 2, 3], (ring, ring), [1], random.Random(seed))
        assert sorted(doors) == sorted(ring)


def test_across_numbers_the_other_level_after_this_one() -> None:
    across = TR.Across(gates=((0, 1), (3, 0)), doors=frozenset({(0, 1)}))
    assert across.links([0, 0, 1, 2]) == {(0, 4), (2, 3), (3, 4)}


def test_a_gate_counts_as_a_door_hop_so_a_ring_joined_below_needs_no_detour() -> None:
    hub = TR.Across(gates=((0, 0), (1, 0), (2, 0), (3, 0))).links([0, 1, 2, 3])
    assert TR.detour_doors(RING, [*PATH, *hub], TR.MAX_HOP, random.Random(0)) == {}
    ring = [(0, 1), (1, 2), (2, 3), (0, 3)]
    for seed in range(8):
        doors = TR.draw_doors([0, 1, 2, 3], (ring, ring), [1], random.Random(seed), hub)
        assert len(doors) == 3


def test_a_gate_link_narrows_the_wall_between_territories_it_brings_close() -> None:
    territory = [0, 0, 1, 2]
    links = TR.Across(gates=((0, 0), (3, 0))).links(territory)
    assert TR.wall_depths(territory, [(1, 2)], 72, links)[(0, 3)] == 3
    assert TR.wall_depths(territory, [(1, 2)], 72)[(0, 3)] == 4


def _count(players: int, land: int, territories: int) -> TerritoryCount:
    return TerritoryCount(players, land, territories)


def test_draw_territory_count_draws_among_the_nearest_records() -> None:
    counts = [_count(2, 4000 + i, 8) for i in range(5)] + [_count(4, 4000, 20)]
    counts += [_count(2, 20000, 30)]
    for seed in range(10):
        assert TR.draw_territory_count(counts, 2, 4000, random.Random(seed)) == 8


def test_draw_territory_count_falls_back_to_the_nearest_player_count_with_enough_maps() -> None:
    counts = [_count(3, 4000, 11)] + [_count(4, 4000 + i, 12) for i in range(5)]
    assert TR.draw_territory_count(counts, 3, 4000, random.Random(0)) == 12
    far = [_count(2, 30000 + i, 25) for i in range(5)]
    assert TR.draw_territory_count(far, 2, 4000, random.Random(0)) == 25
    assert TR.draw_territory_count([], 2, 4000, random.Random(0)) == 3


def test_wall_kinds_keeps_inner_kinds_gates_doors_and_walls_the_rest() -> None:
    territory = [0, 0, 1, 1]
    realised = [(0, 1), (0, 2), (1, 3), (2, 3)]
    inner = {(0, 1): OPEN, (2, 3): CLOSED}
    kinds = TR.wall_kinds(territory, realised, inner, [(0, 2)])
    assert kinds == {(0, 1): OPEN, (0, 2): GATED, (1, 3): CLOSED, (2, 3): CLOSED}


def test_a_wall_widens_with_the_doors_between_its_territories() -> None:
    widths = [TR.wall_width(hops, 72) for hops in (1, 2, 3, 5, None)]
    assert widths == [1, 3, 4, 4, 4]


def test_a_wall_widens_with_the_map_side() -> None:
    assert [TR.wall_width(hops, 144) for hops in (1, 2, None)] == [2, 6, 8]
    assert [TR.wall_width(hops, 36) for hops in (1, 2, None)] == [1, 3, 4]


def test_wall_depths_widen_the_pairs_of_far_territories_only() -> None:
    territory = [0, 0, 1, 2]
    assert TR.wall_depths(territory, [(1, 2), (2, 3)], 72) == {(0, 3): 3, (1, 3): 3}
    assert TR.wall_depths(territory, [(1, 2)], 72) == {(0, 3): 4, (1, 3): 4, (2, 3): 4}


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


def test_a_doorless_home_is_stranded_on_a_land_border_and_islanded_across_water() -> None:
    door = PlannedDoor((0, 1), (0, 1), (0, None), ((0, 0), (1, 0)))
    plan = TerritoryPlan({0: 0, 1: 1, 2: 2}, (0, None, 1), (door,))
    assert TR.stranded(plan, [(0, 1), (1, 2)]) == [1]
    assert TR.islanded(plan, [(0, 1), (1, 2)]) == []
    assert TR.stranded(plan, [(0, 1)]) == []
    assert TR.islanded(plan, [(0, 1)]) == [1]
    assert TR.stranded(TerritoryPlan({0: 0}, (0,), ()), []) == []


def test_a_territory_no_home_reaches_over_the_doors_is_unreached() -> None:
    door = PlannedDoor((0, 1), (0, 1), (0, None), ((0, 0), (1, 0)))
    plan = TerritoryPlan({0: 0, 1: 1, 2: 2, 3: 3}, (0, None, None, None), (door,))
    assert TR.unreached(plan, [(0, 1), (1, 2)]) == [2]
    assert TR.unreached(plan, [(0, 1)]) == []

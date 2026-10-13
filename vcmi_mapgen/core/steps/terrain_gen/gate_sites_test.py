"""Tests for core.steps.terrain_gen.gate_sites (where the Subterranean Gates stand)."""

import math
import random

from vcmi_mapgen.core.steps.terrain_gen.gate_sites import GateGround, plan_gates

HALVES = [[0] * 6 + [1] * 6 for _ in range(6)]
CAVE = [[2] * 12 for _ in range(6)]


def test_a_gate_stands_where_its_whole_room_lies_in_one_zone_pair_off_the_fronts() -> None:
    ground = GateGround((HALVES, CAVE), {(2, 4)}, ((-1, 0), (0, 0)))
    assert ground.zones((3, 1)) == (0, 2)
    assert ground.zones((6, 1)) is None
    assert ground.zones((3, 4)) is None
    assert ground.zones((0, 1)) is None


def test_plan_gates_keeps_one_gate_per_zone_and_the_spacing_floor() -> None:
    ground = GateGround((HALVES, HALVES), frozenset(), ((0, 0),))
    for seed in range(8):
        gates = plan_gates([(1, 1)], ground, (4, 3.0), random.Random(seed))
        assert gates[0] == ((1, 1), (0, 0))
        assert sorted(zones for _, zones in gates) == [(0, 0), (1, 1)]
        assert math.dist(gates[0][0], gates[1][0]) >= 3

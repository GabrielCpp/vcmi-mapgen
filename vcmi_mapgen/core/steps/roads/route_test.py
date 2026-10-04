"""Tests for the cheapest road path."""

from collections.abc import Set as AbstractSet

from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.steps.roads.route import StepCost, route

NONE: frozenset[Tile] = frozenset()


def _open(w: int, h: int, blocked: AbstractSet[Tile] = NONE) -> StepCost:
    def cost(_u: Tile, v: Tile) -> float | None:
        x, y = v
        return 1.0 if 0 <= x < w and 0 <= y < h and v not in blocked else None

    return cost


def test_route_runs_from_a_source_to_a_target() -> None:
    path = route([(0, 0)], {(3, 0)}, _open(4, 1), 0.5)
    assert path == [(0, 0), (1, 0), (2, 0), (3, 0)]


def test_route_prefers_the_path_with_fewer_turns() -> None:
    path = route([(0, 0)], {(3, 3)}, _open(4, 4), 0.5)
    assert path is not None
    assert len(path) == 7
    turns = sum(
        1
        for a, b, c in zip(path, path[1:], path[2:], strict=False)
        if (b[0] - a[0], b[1] - a[1]) != (c[0] - b[0], c[1] - b[1])
    )
    assert turns == 1


def test_route_detours_around_a_blocked_tile() -> None:
    path = route([(0, 1)], {(2, 1)}, _open(3, 3, frozenset({(1, 1)})), 0.0)
    assert path is not None
    assert (1, 1) not in path
    assert len(path) == 5


def test_route_returns_none_when_no_target_is_reachable() -> None:
    wall = frozenset((1, y) for y in range(3))
    assert route([(0, 1)], {(2, 1)}, _open(3, 3, wall), 0.5) is None


def test_route_starts_at_a_source_already_on_the_target() -> None:
    assert route([(1, 1)], {(1, 1)}, _open(3, 3), 0.5) == [(1, 1)]

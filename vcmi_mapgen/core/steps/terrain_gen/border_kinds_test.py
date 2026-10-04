"""Tests for core.steps.terrain_gen.border_kinds (the kind of every realised border)."""

import random

from vcmi_mapgen.core.reading.borders import AdjacencyKind
from vcmi_mapgen.core.reading.places import PlaceRole
from vcmi_mapgen.core.steps.terrain_gen import border_kinds as BK

CLOSED, GATED, OPEN = AdjacencyKind.CLOSED, AdjacencyKind.GATED, AdjacencyKind.OPEN
H, M = PlaceRole.HOME, PlaceRole.MIDDLE

TABLE = {
    "home|middle|closed": 1,
    "home|middle|gated": 3,
    "middle|middle|closed": 6,
    "middle|middle|open": 2,
}


def test_kind_weights_read_the_pair_or_pool_every_pair() -> None:
    assert BK.kind_weights(TABLE, M, H) == {CLOSED: 1.0, GATED: 3.0, OPEN: 0.0}
    assert BK.kind_weights(TABLE, H, H) == {CLOSED: 7.0, GATED: 3.0, OPEN: 2.0}


def test_draw_kind_stays_in_the_allowed_kinds() -> None:
    weights = {CLOSED: 5.0, GATED: 1.0, OPEN: 1.0}
    drawn = [BK.draw_kind(random.Random(s), weights, BK.PASSABLE) for s in range(50)]
    assert set(drawn) <= set(BK.PASSABLE)
    assert drawn == [BK.draw_kind(random.Random(s), weights, BK.PASSABLE) for s in range(50)]
    assert BK.draw_kind(random.Random(0), {CLOSED: 1.0}, BK.PASSABLE) == GATED


def _connected(nodes: set[int], edges: frozenset[tuple[int, int]]) -> bool:
    parent = {n: n for n in nodes}

    def root(x: int) -> int:
        while parent[x] != x:
            x = parent[x]
        return x

    for p, q in edges:
        parent[root(q)] = root(p)
    return len({root(n) for n in nodes}) == 1


def test_spanning_forest_spans_and_prefers_planned_edges() -> None:
    edges = [(0, 1), (1, 2), (0, 2), (2, 3), (3, 4), (2, 4)]
    planned = {(0, 2), (2, 4)}
    for seed in range(20):
        span = BK.spanning_forest(edges, planned, lambda _e: 1.0, random.Random(seed))
        assert len(span) == 4
        assert _connected({0, 1, 2, 3, 4}, span)
        assert planned <= span


def test_spanning_forest_spans_each_component() -> None:
    edges = [(0, 1), (1, 2), (5, 6)]
    span = BK.spanning_forest(edges, (), lambda _e: 0.0, random.Random(1))
    assert span == frozenset(edges)


def test_draw_kinds_keep_every_place_reachable() -> None:
    roles = {0: H, 1: M, 2: M, 3: M, 4: H}
    realised = [(0, 1), (1, 2), (0, 2), (2, 3), (3, 4), (2, 4), (1, 3)]
    planned = {(0, 1), (1, 2), (2, 3), (3, 4)}
    for seed in range(30):
        kinds = BK.draw_kinds(roles, realised, planned, TABLE, random.Random(seed))
        assert set(kinds) == set(realised)
        assert all(kinds[e] == CLOSED for e in realised if e not in planned)
        passable = frozenset(e for e, k in kinds.items() if k != CLOSED)
        assert _connected(set(roles), passable)
        assert kinds == BK.draw_kinds(roles, realised, planned, TABLE, random.Random(seed))

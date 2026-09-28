"""Reliability tests for the corpus gate estimator and gate spreading."""

import math
import random
from collections.abc import Callable
from itertools import combinations

from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.priors.gates import GateStats
from vcmi_mapgen.core.steps.gameplay.gate_pairs import GateSide, gate_anchors

S = 40


def _stats(counts: tuple[int, ...], frac: float = 0.25) -> GateStats:
    return GateStats(counts_by_size={S: counts}, min_gap_frac=frac, n_maps=len(counts))


def _side(zone_of: dict[Tile, int]) -> GateSide:
    return GateSide(frozenset(zone_of), set(), zone_of=zone_of)


def _anchors(sides: tuple[GateSide, GateSide], stats: GateStats, seed: int) -> list[Tile]:
    return gate_anchors(sides, stats, S, seed, lambda c, _spread: c)


def _open(label: Callable[[int, int], int]) -> dict[Tile, int]:
    return {(x, y): label(x, y) for x in range(S) for y in range(S)}


def test_draw_count_uses_nearest_corpus_width() -> None:
    st = GateStats(counts_by_size={36: (1,), 108: (7,)}, min_gap_frac=0.0, n_maps=2)
    assert st.draw_count(40, random.Random(0)) == 1
    assert st.draw_count(100, random.Random(0)) == 7


def test_at_most_one_gate_per_zone_on_each_level() -> None:
    """Two surface zones cap the map at two gates even when the corpus asks for more."""
    stats = _stats((6,), frac=0.0)
    side0 = _side(_open(lambda x, _y: int(x >= S // 2)))
    side1 = _side(_open(lambda x, y: x // 10 + 4 * (y // 10)))
    for seed in range(20):
        anchors = _anchors((side0, side1), stats, seed)
        assert len({side0.zone_of[a] for a in anchors}) == len(anchors) <= 2
        assert len({side1.zone_of[a] for a in anchors}) == len(anchors)


def test_gates_keep_the_corpus_spacing_floor() -> None:
    """With one zone per tile nothing but the spacing floor keeps gates apart."""
    stats = _stats((6,), frac=0.25)
    zone_of = _open(lambda x, y: x * S + y)
    for seed in range(20):
        anchors = _anchors((_side(zone_of), _side(zone_of)), stats, seed)
        assert anchors
        assert all(math.dist(a, b) >= 0.25 * S for a, b in combinations(anchors, 2))


def test_gate_count_never_exceeds_the_draw() -> None:
    stats = _stats((1, 2), frac=0.0)
    zone_of = _open(lambda x, y: x * S + y)
    for seed in range(20):
        assert 1 <= len(_anchors((_side(zone_of), _side(zone_of)), stats, seed)) <= 2

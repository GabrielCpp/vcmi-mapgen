from itertools import pairwise

import pytest

from vcmi_mapgen.core.priors.effort import (
    BANDS,
    CORPUS_EDGES,
    DEFAULT_EDGES,
    DEFAULT_TOLL,
    BandEdgeError,
    EffortPriors,
    extend_edges,
    toll_growth,
)


def test_a_band_starts_at_its_edge() -> None:
    priors = EffortPriors()
    assert [priors.band(t) for t in (0, 7, 8, 12, 13, 21, 22, 33)] == [1, 1, 2, 2, 3, 3, 4, 4]
    assert priors.band(DEFAULT_EDGES[-1] - 1) == BANDS - 1
    assert priors.band(10_000) == BANDS


def test_the_edges_past_the_corpus_grow_by_the_toll() -> None:
    growth = toll_growth(DEFAULT_TOLL)
    assert 1.5 < growth < 1.6
    assert DEFAULT_EDGES[: len(CORPUS_EDGES)] == CORPUS_EDGES
    assert len(DEFAULT_EDGES) == BANDS - 1
    assert DEFAULT_EDGES[3:] == tuple(round(22 * growth**k) for k in range(1, 5))
    assert all(1.5 < b / a < 1.6 for a, b in pairwise(DEFAULT_TOLL[7:]))
    assert extend_edges((8, 13, 22), (0, 1, 1, 1), 6) == (8, 13, 22, 23, 24)


def test_edges_that_do_not_rise_are_refused() -> None:
    with pytest.raises(BandEdgeError):
        _ = EffortPriors(edges=(8, 8, *DEFAULT_EDGES[2:]))
    with pytest.raises(BandEdgeError):
        _ = EffortPriors(edges=(8, 13, 22))


def test_each_band_has_one_offer() -> None:
    with pytest.raises(BandEdgeError):
        _ = EffortPriors(baskets=({"treasure": 1},))
    with pytest.raises(BandEdgeError):
        _ = EffortPriors(boxes=(0, 1))
    offer = EffortPriors().offer(4)
    assert offer.basket == {"major": 1, "relic": 3}
    assert min(offer.grant.levels) >= 6 and offer.boxes >= 1
    assert EffortPriors().offer(BANDS).basket == {"relic": 1}


def test_the_grant_climbs_band_by_band() -> None:
    grants = EffortPriors().grants
    assert all(max(a.levels) <= max(b.levels) for a, b in pairwise(grants))
    assert all(min(a.levels) <= min(b.levels) for a, b in pairwise(grants))
    assert all(max(a.gold) <= max(b.gold) for a, b in pairwise(grants))
    assert all(a.creatures[1] <= b.creatures[1] for a, b in pairwise(grants[3:]))


def test_the_relic_share_rises_past_the_corpus_bands() -> None:
    baskets = EffortPriors().baskets
    shares = [b.get("relic", 0) / sum(b.values()) for b in baskets[3:]]
    assert all(a < b for a, b in pairwise(shares))

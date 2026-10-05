from itertools import pairwise

import pytest

from vcmi_mapgen.core.priors.effort import BandEdgeError, EffortPriors


def test_a_band_starts_at_its_edge() -> None:
    priors = EffortPriors(edges=(8, 13, 22))
    assert [priors.band(t) for t in (0, 7, 8, 12, 13, 21, 22, 90)] == [1, 1, 2, 2, 3, 3, 4, 4]


def test_edges_that_do_not_rise_are_refused() -> None:
    with pytest.raises(BandEdgeError):
        _ = EffortPriors(edges=(8, 8, 22))
    with pytest.raises(BandEdgeError):
        _ = EffortPriors(edges=(8, 13))


def test_each_band_has_one_offer() -> None:
    with pytest.raises(BandEdgeError):
        _ = EffortPriors(baskets=({"treasure": 1},))
    with pytest.raises(BandEdgeError):
        _ = EffortPriors(boxes=(0, 1))
    offer = EffortPriors().offer(4)
    assert offer.basket == {"major": 1, "relic": 3}
    assert min(offer.grant.levels) >= 6 and offer.boxes >= 1


def test_the_grant_climbs_band_by_band() -> None:
    grants = EffortPriors().grants
    assert all(max(a.levels) < min(b.levels) for a, b in pairwise(grants))
    assert all(max(a.gold) <= max(b.gold) for a, b in pairwise(grants))

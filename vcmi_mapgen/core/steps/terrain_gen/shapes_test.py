"""Tests for the place shapes on the ground."""

import random

from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.steps.terrain_gen.shapes import grow_shapes, shape_caps, spread_anchors


def test_the_caps_share_the_land_among_the_corpus_place_count(priors: Priors) -> None:
    caps = shape_caps(priors.places[0], 2, (5184, 5184), random.Random(1))
    assert len(caps) >= 5
    assert abs(sum(caps) - 5184) < 5184 * 0.2


def test_the_anchors_are_distinct_on_the_largest_mass() -> None:
    land = [[x > 2 for x in range(30)] for _ in range(30)]
    anchors = spread_anchors(land, 8, random.Random(2))
    assert len(set(anchors)) == 8
    assert all(x > 2 for x, _ in anchors)
    assert len(spread_anchors([[True, True]], 5, random.Random(0))) == 2


def test_the_shapes_cover_the_land_with_one_place_per_cap() -> None:
    land = [[True] * 36 for _ in range(36)]
    layout = grow_shapes(land, [216] * 6, random.Random(3))
    assert all(z >= 0 for row in layout.label for z in row)
    assert layout.places == 6
    assert layout == grow_shapes(land, [216] * 6, random.Random(3))

"""The place shapes on the ground (map-math 4.2): a corpus place count and size mix for the
land, anchors spread over the largest land mass, and the regions grown from them. Nothing
here knows a role, an owner or a border the shapes should realise."""

import random
from collections.abc import Sequence
from typing import cast

import numpy as np

from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.priors.places import PlaceStats
from vcmi_mapgen.core.steps.terrain_gen.layout import Land, Layout, grow, main_land
from vcmi_mapgen.core.steps.terrain_gen.place_draws import draw_roles, draw_sizes, place_count

CANDIDATES = 10
"""How many random land tiles each anchor after the first chooses among."""


def shape_caps(
    stats: PlaceStats, players: int, land: tuple[int, int], rng: random.Random
) -> list[int]:
    """The target size of each place, in random order. ``land`` holds the land count the
    place count reads, then the land tiles the sizes share. The count comes from the
    corpus records nearest ``players`` and that land, and the sizes from the corpus size
    fractions of a role mix with one home per player."""
    planned, tiles = land
    n = place_count(stats.counts, players, planned, rng)
    caps = draw_sizes(stats, draw_roles(stats, n, players, rng), tiles, rng)
    rng.shuffle(caps)
    return caps


def spread_anchors(land: Land, n: int, rng: random.Random) -> list[Tile]:
    """``n`` distinct anchors on the largest land mass, fewer when it has fewer tiles. The
    first is a random tile. Each next one is the farthest from the anchors before it among
    ``CANDIDATES`` random tiles, or the farthest of all tiles when every candidate is
    taken."""
    mass = main_land(land)
    tiles = [(x, y) for y, row in enumerate(mass) for x, v in enumerate(row) if v]
    xs = np.array([x for x, _ in tiles], dtype=np.float64)
    ys = np.array([y for _, y in tiles], dtype=np.float64)
    near = np.full(len(tiles), np.inf)
    out: list[Tile] = []
    for _ in range(min(n, len(tiles))):
        far = cast("list[float]", near.tolist())
        picks = rng.sample(range(len(tiles)), min(CANDIDATES, len(tiles)))
        best = max(picks, key=lambda j: (far[j], -j))
        if far[best] <= 0:
            best = int(np.argmax(near))
        x, y = tiles[best]
        out.append((x, y))
        near = np.minimum(near, (xs - x) ** 2 + (ys - y) ** 2)
    return out


def grow_shapes(land: Land, caps: Sequence[int], rng: random.Random) -> Layout:
    """One place per cap grown from anchors spread over the largest land mass, each up to
    its cap, then one pocket per piece of land no anchor reached. It never retries."""
    anchors = spread_anchors(land, len(caps), rng)
    return grow(land, anchors, caps[: len(anchors)], rng)

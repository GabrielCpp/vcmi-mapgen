"""The palette partition on small literal place graphs."""

import random

from vcmi_mapgen.core.priors.places import PaletteCount
from vcmi_mapgen.core.steps.terrain_gen.palette import (
    components,
    group_places,
    neighbours,
    palette_count,
)

GRID = 5
SIZES = [10 + (i % 7) for i in range(GRID * GRID)]
LATTICE = frozenset(
    (y * GRID + x, y * GRID + x + dx + GRID * dy)
    for y in range(GRID)
    for x in range(GRID)
    for dx, dy in ((1, 0), (0, 1))
    if x + dx < GRID and y + dy < GRID
)
TWO_PIECES = frozenset({(0, 1), (1, 2), (3, 4), (4, 5), (5, 6)})
AREAS = [40, 80, 120, 300, 2000]


def _connected(group: list[int], adjacency: frozenset[tuple[int, int]], r: int) -> bool:
    members = [p for p, g in enumerate(group) if g == r]
    inside = frozenset((a, b) for a, b in adjacency if group[a] == r and group[b] == r)
    sub = neighbours(len(group), inside)
    return any(sorted(members) == comp for comp in components(sub))


def test_regions_cover_every_place_and_stay_connected() -> None:
    for seed in range(20):
        group = group_places(SIZES, LATTICE, 6, AREAS, random.Random(seed))
        assert -1 not in group
        assert sorted(set(group)) == list(range(6))
        assert all(_connected(group, LATTICE, r) for r in range(6))


def test_each_component_gets_a_region_and_k_is_respected() -> None:
    for seed in range(20):
        group = group_places([12] * 7, TWO_PIECES, 3, AREAS, random.Random(seed))
        assert len(set(group)) == 3
        assert set(group[:3]).isdisjoint(group[3:])
        assert all(_connected(group, TWO_PIECES, r) for r in range(3))
    assert len(set(group_places([12] * 7, TWO_PIECES, 1, AREAS, random.Random(0)))) == 2


def test_the_same_stream_gives_the_same_partition() -> None:
    first = group_places(SIZES, LATTICE, 5, AREAS, random.Random(7))
    assert group_places(SIZES, LATTICE, 5, AREAS, random.Random(7)) == first


def test_palette_count_scales_the_nearest_record_and_keeps_the_floor() -> None:
    counts = [PaletteCount(6, 24, 4000), PaletteCount(2, 8, 900)]
    rng = random.Random(0)
    assert {palette_count(counts[:1], 12, 4000, 1, rng) for _ in range(5)} == {3}
    assert palette_count(counts[1:], 8, 900, 4, rng) == 4
    assert palette_count(counts[1:], 3, 900, 1, rng) == 1

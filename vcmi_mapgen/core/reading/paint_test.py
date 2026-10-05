"""Paint readings on small literal grids: bands, raw cuts, shares, accents and widths."""

from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.reading.paint import (
    Accent,
    accents,
    band_tiles,
    border_depth,
    half_depth,
    read_paint,
    transition_width,
)

G, S, D = Terrain.GRASS, Terrain.SNOW, Terrain.DIRT
DOMINANT = {0: G, 1: S}


def halves(width: int, height: int) -> list[list[int]]:
    return [[0 if x < width // 2 else 1 for x in range(width)] for _ in range(height)]


def coated(label: list[list[int]]) -> list[list[Terrain]]:
    return [[DOMINANT[z] for z in row] for row in label]


def test_a_sharp_edge_is_a_raw_cut_until_its_border_tiles_are_excused() -> None:
    label = halves(8, 4)
    terrain = coated(label)
    depth = border_depth(label, [(0, 1)])
    edge = band_tiles(label, depth, {(0, 1): 0})
    assert edge == {(x, y) for y in range(4) for x in (3, 4)}
    assert band_tiles(label, depth, {(0, 1): 2}) == {(x, y) for y in range(4) for x in range(2, 6)}
    assert read_paint(terrain, label, DOMINANT, ()).raw_cut == 4
    reading = read_paint(terrain, label, DOMINANT, edge)
    assert (reading.raw_cut, reading.border, reading.violations) == (0, 4, 0)


def test_an_inner_patch_is_an_accent_and_a_patch_on_the_border_a_violation() -> None:
    label = halves(8, 4)
    terrain = coated(label)
    terrain[1][1] = D
    assert accents(terrain, label, DOMINANT) == [Accent(0, D, frozenset({(1, 1)}))]
    terrain[2][3] = D
    reading = read_paint(terrain, label, DOMINANT, ())
    assert reading.violations == 1
    assert reading.shares[0] == 14 / 16
    assert read_paint(terrain, label, DOMINANT, {(3, 2)}).violations == 0


def test_a_graded_border_counts_every_mixed_level_on_both_sides() -> None:
    label = halves(12, 10)
    terrain = coated(label)
    for y in range(10):
        if y % 2:
            terrain[y][5], terrain[y][6] = S, G
        if y < 3:
            terrain[y][4], terrain[y][7] = S, G
    depth = border_depth(label, [(0, 1)])
    width = transition_width(terrain, label, depth, (0, 1), (G, S))
    assert width == 4
    assert half_depth(width) == 2

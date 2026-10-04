"""Tests for Paint on small literal grids."""

import random

from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.priors.markov import MarkovTables, empty_tables
from vcmi_mapgen.core.reading.paint import dominant_shares
from vcmi_mapgen.core.reading.places import PlaceRole
from vcmi_mapgen.core.steps.terrain_gen.paint import (
    Budget,
    Canvas,
    PaintPriors,
    crossing_chance,
    grade_bands,
    grow_accents,
    inner_tiles,
    paint_places,
)
from vcmi_mapgen.core.steps.terrain_gen.result import LevelPlaces, PlannedPlace

G, S, D = Terrain.GRASS, Terrain.SNOW, Terrain.DIRT
THIN = (Terrain.DIRT, Terrain.SAND, Terrain.SUBTERRANEAN)


def halves(width: int, height: int) -> list[list[int]]:
    return [[0 if x < width // 2 else 1 for x in range(width)] for _ in range(height)]


def canvas_of(label: list[list[int]], theta: float) -> Canvas:
    dominant = {0: G, 1: S}
    work = [[dominant[z].value for z in row] for row in label]
    return Canvas(work, label, dominant, Budget(label, theta))


def base(label: list[list[int]]) -> list[list[Terrain]]:
    return [[G if z == 0 else S for z in row] for row in label]


def dirt_beside(*kinds: Terrain, flip: int = 50) -> MarkovTables:
    tables = empty_tables()
    for d in kinds:
        tables.chain4.horiz[d.value, d.value][D.value] = flip
        tables.chain4.horiz[d.value, d.value][d.value] = 100
        tables.chain4.vert[d.value, d.value][d.value] = 100
    return tables


def priors_of(theta: float, rate: float, tables: MarkovTables) -> PaintPriors:
    return PaintPriors(theta, (5,), {G: rate, S: 0.0}, {G: (6,), S: (6,)}, tables)


def two_places(label: list[list[int]]) -> LevelPlaces:
    places = {0: PlannedPlace(PlaceRole.HOME, 0, G), 1: PlannedPlace(PlaceRole.MIDDLE, None, S)}
    return LevelPlaces(label, places, frozenset({(0, 1)}))


def test_an_accent_stays_inside_its_place_and_off_its_boundary() -> None:
    label = halves(20, 20)
    canvas = canvas_of(label, 0.5)
    band = grade_bands(canvas, {(0, 1): 0}, random.Random(1))
    grow_accents(canvas, inner_tiles(label, band), priors_of(0.5, 50.0, dirt_beside(G)), 4)
    changed = [
        (x, y) for y, row in enumerate(canvas.work) for x, t in enumerate(row) if t == D.value
    ]
    assert changed
    assert all(label[y][x] == 0 and x < 9 for x, y in changed)


def test_a_band_grades_each_side_into_the_other_and_stops_at_its_depth() -> None:
    label = halves(12, 200)
    canvas = canvas_of(label, 0.0)
    band = grade_bands(canvas, {(0, 1): 3}, random.Random(7))
    assert band == {(x, y) for y in range(200) for x in range(3, 9)}
    crossed = {
        depth: sum(canvas.work[y][5 - depth] == S.value for y in range(200)) for depth in range(4)
    }
    assert crossed[0] > crossed[1] > crossed[2]
    assert crossed[3] == 0
    assert crossing_chance(0, 3) > crossing_chance(2, 3) > 0


def test_every_place_keeps_its_dominant_share_at_the_floor() -> None:
    label = halves(24, 24)
    priors = priors_of(0.8, 80.0, dirt_beside(G, S, flip=400))
    painted = paint_places(base(label), two_places(label), priors, 3, THIN)
    shares = dominant_shares(painted.grid, label, {0: G, 1: S})
    assert min(shares.values()) >= 0.8
    assert min(shares.values()) < 1.0


def test_the_same_seed_paints_the_same_grid() -> None:
    label = halves(24, 24)
    priors = priors_of(0.6, 10.0, dirt_beside(G, S))
    grid = base(label)
    first = paint_places(grid, two_places(label), priors, 9, THIN)
    again = paint_places(grid, two_places(label), priors, 9, THIN)
    other = paint_places(grid, two_places(label), priors, 10, THIN)
    assert first == again
    assert first.grid != other.grid

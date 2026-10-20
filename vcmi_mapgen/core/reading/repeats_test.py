import math

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState, PlacedObject
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.reading.repeats import (
    copy_spacing,
    copy_u,
    kind_key,
    kind_of,
    nearest_copies,
    repeat_share,
)


def _visit(catalog: Catalog, x: int, y: int, level: int = 0, n: int = 0) -> PlacedObject:
    ident = catalog.candidates(Purpose.MANA, "grass")[n]
    return PlacedObject(x, y, level, Purpose.MANA, ident.kind, ident.footprint)


def test_each_repeated_visitable_counts_tiles_to_its_nearest_copy(catalog: Catalog) -> None:
    objs = [_visit(catalog, 10, 10), _visit(catalog, 14, 12), _visit(catalog, 30, 10)]
    assert nearest_copies(catalog, objs) == [4, 4, 16]


def test_a_copy_on_another_level_is_no_copy(catalog: Catalog) -> None:
    objs = [_visit(catalog, 10, 10), _visit(catalog, 11, 10, 1)]
    assert nearest_copies(catalog, objs) == []


def test_the_share_counts_the_gaps_within_reach() -> None:
    assert repeat_share([4, 4, 16], 6) == 2 / 3
    assert repeat_share([], 6) == 0.0


def _state(objs: list[PlacedObject], land: int = 100) -> MapState:
    size = 10
    cells = [Terrain.GRASS] * land + [Terrain.WATER] * (size * size - land)
    grid = [cells[y * size : (y + 1) * size] for y in range(size)]
    return MapState(size, terrain={0: grid, 1: grid}, objs=objs)


def test_u_scales_with_the_square_of_the_distance() -> None:
    assert copy_u(2.0, 4, 100) == 4 * math.pi * 4.0 / 100
    assert copy_u(0.0, 4, 100) == 0.0


def test_a_kind_key_writes_an_absent_part_empty() -> None:
    assert kind_key(("windmill", None)) == "windmill:"
    assert kind_key(("mine", "sawmill")) == "mine:sawmill"


def test_each_copy_reads_u_from_its_euclidean_nearest_copy(catalog: Catalog) -> None:
    objs = [_visit(catalog, 1, 1), _visit(catalog, 4, 5), _visit(catalog, 9, 9, 1)]
    got = copy_spacing(catalog, _state(objs))
    u = copy_u(5.0, 2, 100)
    assert got == [
        (kind_of(catalog.identity_of(objs[0].kind)), Purpose.MANA, u),
        (kind_of(catalog.identity_of(objs[1].kind)), Purpose.MANA, u),
    ]


def test_a_level_without_land_reads_no_spacing(catalog: Catalog) -> None:
    objs = [_visit(catalog, 1, 1), _visit(catalog, 4, 5)]
    assert copy_spacing(catalog, _state(objs, land=0)) == []

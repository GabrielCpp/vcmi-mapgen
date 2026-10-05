"""Hemmed reading on a small literal grid: a mine between two rocks is hemmed, an open one
is not."""

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Footprint, MapState, PlacedObject, Role
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.reading.flanks import Hemmed, read_hemmed

SIZE = 12


def _obj(t: tuple[int, int], purpose: str, role: Role) -> PlacedObject:
    return PlacedObject(t[0], t[1], 0, purpose, purpose.lower(), Footprint.one(role))


def test_a_mine_between_two_rocks_is_hemmed_and_an_open_one_is_not(catalog: Catalog) -> None:
    grid = [[Terrain.GRASS] * SIZE for _ in range(SIZE)]
    rocks = [_obj(t, Purpose.DECORATION, Role.BLOCKING) for t in ((2, 3), (4, 3), (8, 3))]
    mines = [_obj(t, Purpose.MINE, Role.VISIT) for t in ((3, 3), (7, 7))]
    state = MapState(size=SIZE, terrain={0: grid}, objs=rocks + mines)
    assert read_hemmed(catalog, state, 0) == Hemmed(1, 2)
    assert Hemmed(1, 2).share == 0.5
    assert Hemmed().share is None

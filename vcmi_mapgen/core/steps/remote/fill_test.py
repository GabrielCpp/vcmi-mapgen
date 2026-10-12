import numpy as np

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Footprint, Identity, PlacedObject, Role, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.placement.site import LevelField, SiteZone
from vcmi_mapgen.core.priors.gameplay import TerrainStats
from vcmi_mapgen.core.reading.remote import free_land, level_distance, remote_runs
from vcmi_mapgen.core.steps.remote.fill import (
    RemoteLevel,
    approaches,
    fill_level,
    landings,
    spot_order,
)

_ONE = Identity("t", "s", "X", Footprint.one(Role.VISIT))
_TREE = Identity("pine", "pine", "pine", Footprint.one(Role.BLOCKING))
_ST = TerrainStats(0, {}, {}, {}, {}, {}, [], [], [], 0.0, {})
GRASS, WATER, ROCK = int(Terrain.GRASS), int(Terrain.WATER), int(Terrain.ROCK)


def _obj(xy: Tile, purpose: str, ident: Identity = _ONE) -> PlacedObject:
    return PlacedObject.at(ident, xy, purpose=purpose)


def test_landings_mark_the_shore_of_a_part_the_web_never_reaches() -> None:
    """Columns 0-2 hold the web, column 3 is water, columns 4-6 are an island part of the
    same zone, column 7 is rock: the island's landings are its shore column."""
    grid = [[GRASS] * 3 + [WATER] + [GRASS] * 3 + [ROCK] for _ in range(5)]
    passable = {(x, y) for x in (0, 1, 2, 4, 5, 6) for y in range(5)}
    unwalkable = {(x, y) for x in (3, 7) for y in range(5)}
    found = landings(passable, {(0, 2)}, grid, unwalkable)
    assert found == {(4, y) for y in range(5)}


def test_a_part_beside_another_zone_lands_on_its_border() -> None:
    grid = [[GRASS] * 6 for _ in range(3)]
    passable = {(x, y) for x in (0, 1, 4, 5) for y in range(3)}
    unwalkable = {(2, y) for y in range(3)}
    assert landings(passable, {(0, 0)}, grid, unwalkable) == set()
    found = landings(passable - {(0, 0), (1, 0)}, {(4, 1)}, grid, unwalkable)
    assert found == {(0, 1), (1, 1)}


def test_approaches_keep_doors_but_not_guards_or_scenery() -> None:
    objs = [
        _obj((2, 2), Purpose.RESOURCE_PILE),
        _obj((6, 6), Purpose.GUARD),
        _obj((8, 0), Purpose.DECORATION),
        _obj((0, 8), "", _TREE),
    ]
    kept = approaches(objs, {(1, 1)}, 10)
    assert kept == {(x, y) for x in (1, 2, 3) for y in (1, 2, 3)} - {(1, 1)}


def test_spot_order_takes_the_farthest_tile_first() -> None:
    distance = np.zeros((4, 4), dtype=np.int64)
    distance[1, 2] = 3
    distance[3, 0] = 3
    distance[0, 0] = 1
    tiles = frozenset({(0, 0), (2, 1), (0, 3), (3, 3)})
    assert spot_order(tiles, distance) == [(0, 3), (2, 1), (0, 0), (3, 3)]


def _level(walk: frozenset[Tile] | None = None) -> RemoteLevel:
    size = 20
    grid = [[GRASS] * size for _ in range(size)]
    objs = [_obj((1, 1), Purpose.TOWN)]
    ts = frozenset((x, y) for x in range(size) for y in range(size))
    prot = frozenset((x, 10) for x in range(size))
    passable = ts if walk is None else walk
    zone = SiteZone("grass", _ST, ts, frozenset(), prot, ts - prot, passable)
    lf = LevelField.build(0, grid, objs)
    kept = approaches(objs, lf.unwalkable, size)
    zone_of = dict.fromkeys(ts, 1)
    return RemoteLevel(0, grid, objs, zone_of, {1: zone}, lf, kept, frozenset(), 5)


def test_fill_level_leaves_no_far_run(catalog: Catalog) -> None:
    lv = _level()
    fill = fill_level(catalog, lv, seed=3)
    assert fill.objs and not fill.log
    objs = [*lv.objs, *fill.objs]
    assert remote_runs(level_distance(objs, 20), free_land(lv.grid, objs), 5) == []
    again = fill_level(catalog, _level(), seed=3)
    assert again.objs == fill.objs


def test_a_run_no_hero_reaches_is_logged_and_left(catalog: Catalog) -> None:
    lv = _level(frozenset((x, y) for x in range(20) for y in range(8, 13)))
    fill = fill_level(catalog, lv, seed=3)
    assert fill.log and all("zone 1" in line for line in fill.log)
    objs = [*lv.objs, *fill.objs]
    assert remote_runs(level_distance(objs, 20), free_land(lv.grid, objs), 5)

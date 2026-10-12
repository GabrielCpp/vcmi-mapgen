import numpy as np

from vcmi_mapgen.core.model import Footprint, Identity, PlacedObject, Role, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.priors.remote import RemotePriors
from vcmi_mapgen.core.reading.remote import (
    free_land,
    level_distance,
    remote_runs,
    remote_share,
    worth_cells,
)

_ONE = Identity("t", "s", "X", Footprint.one(Role.VISIT))
_TREE = Identity("pine", "pine", "pine", Footprint.one(Role.BLOCKING))


def _obj(xy: Tile, purpose: str, ident: Identity = _ONE) -> PlacedObject:
    return PlacedObject.at(ident, xy, purpose=purpose)


def test_guards_signs_and_portals_are_not_worth_the_walk() -> None:
    objs = [
        _obj((1, 1), Purpose.MINE),
        _obj((5, 5), Purpose.GUARD),
        _obj((6, 6), Purpose.INFO),
        _obj((7, 7), Purpose.TRANSPORT),
        _obj((8, 8), "", _TREE),
    ]
    assert worth_cells(objs, 10) == [(1, 1)]
    distance = level_distance(objs, 10)
    assert distance[1, 1] == 0 and distance[5, 5] == 4 and distance[9, 9] == 8


def test_free_land_skips_water_blockers_and_purposed_cells() -> None:
    grid = [[int(Terrain.GRASS)] * 4 for _ in range(4)]
    grid[0][3] = int(Terrain.WATER)
    objs = [_obj((1, 1), "", _TREE), _obj((2, 2), Purpose.GUARD), _obj((0, 3), "")]
    free = free_land(grid, objs)
    assert not free[0, 3] and not free[1, 1] and not free[2, 2]
    assert free[3, 0] and free[0, 0]


def test_runs_are_king_connected_and_largest_first() -> None:
    free = np.zeros((8, 8), dtype=np.bool_)
    for x, y in ((0, 0), (1, 1), (2, 2), (6, 6)):
        free[y, x] = True
    distance = np.full((8, 8), 9, dtype=np.int64)
    distance[1, 1] = 12
    runs = remote_runs(distance, free, 5)
    assert [len(r.tiles) for r in runs] == [3, 1]
    assert runs[0].heart == (1, 1) and runs[0].depth == 12
    assert runs[1].heart == (6, 6)
    assert remote_runs(distance, free, 13) == []


def test_share_counts_free_land_past_the_reach() -> None:
    free = np.ones((2, 2), dtype=np.bool_)
    distance = np.array([[0, 5], [5, 6]], dtype=np.int64)
    assert remote_share(distance, free, 5) == 0.75
    assert remote_share(distance, np.zeros((2, 2), dtype=np.bool_), 5) == 0.0


def test_remote_reach_takes_the_nearest_corpus_size() -> None:
    priors = RemotePriors({36: 4, 72: 5, 144: 6})
    assert priors.at(34) == 4 and priors.at(90) == 5 and priors.at(108) == 5
    assert priors.at(200) == 6

"""The territory miner keeps each map's territory count beside its players and land, and
the saved table loads back the same."""

from pathlib import Path

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Footprint, MapState, PlacedObject, Role
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.corpus.mine.territories import mine_territories
from vcmi_mapgen.corpus.territories import load_territories, save_territories

SIZE = 15
WALL_X = 7
GAP = (WALL_X, 7)


def _map(catalog: Catalog) -> MapState:
    wall = [
        PlacedObject(WALL_X, y, 0, Purpose.DECORATION, "wall", Footprint.one(Role.BLOCKING))
        for y in range(SIZE)
        if y != GAP[1]
    ]
    guard = PlacedObject.at(catalog.identity_of("avwmon3"), GAP, purpose=Purpose.UNKNOWN)
    grid = [[Terrain.GRASS] * SIZE for _ in range(SIZE)]
    return MapState(size=SIZE, terrain={0: grid}, objs=[*wall, guard])


def test_each_map_records_its_territories_beside_its_players_and_land(
    catalog: Catalog,
) -> None:
    stats = mine_territories(catalog, 0, [_map(catalog)], [{}], [3])
    (count,) = stats.counts_by_map
    assert count.players == 3
    assert count.territories == 2
    assert count.land > SIZE * (SIZE - 2)


def test_the_saved_counts_load_back_the_same(catalog: Catalog, tmp_path: Path) -> None:
    stats = mine_territories(catalog, 0, [_map(catalog)], [{}], [2])
    save_territories(tmp_path, {0: stats})
    assert load_territories(tmp_path)[0].counts_by_map == stats.counts_by_map

"""The territory miner keeps each map's territory count beside its players, land and
prizes, and the saved table loads back the same."""

from pathlib import Path

import pytest

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Footprint, MapState, PlacedObject, Role
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.priors.territories import TerritoryCount
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


def test_each_map_counts_the_objects_worth_a_mine_as_prizes(catalog: Catalog) -> None:
    state = _map(catalog)
    ident = catalog.mines_by_resource("grass")["goldMine"][0]
    state.objs.append(PlacedObject(10, 12, 0, Purpose.MINE, ident.kind, ident.footprint))
    state.objs.append(PlacedObject(3, 3, 1, Purpose.MINE, ident.kind, ident.footprint))
    (count,) = mine_territories(catalog, 0, [state], [{}], [2]).counts_by_map
    assert count.prizes == 1
    assert count.prize_tiles == count.land


def test_the_saved_counts_load_back_the_same(catalog: Catalog, tmp_path: Path) -> None:
    stats = mine_territories(catalog, 0, [_map(catalog)], [{}], [2])
    save_territories(tmp_path, {0: stats})
    assert load_territories(tmp_path)[0].counts_by_map == stats.counts_by_map


def test_a_level_without_land_or_prizes_has_no_prize_floor() -> None:
    assert TerritoryCount(2, 100, 3, (), 90, 4).prize_tiles == 25
    assert TerritoryCount(2, 100, 3, (), 90, 0).prize_tiles is None
    assert TerritoryCount(2, 0, 3, (), 0, 4).prize_tiles is None


def test_each_map_keeps_its_territories_as_sites_with_shares_and_owners(
    catalog: Catalog,
) -> None:
    stats = mine_territories(catalog, 0, [_map(catalog)], [{}], [2])
    (plan,) = stats.plans_by_map
    assert plan.record == stats.counts_by_map[0]
    assert len(plan.sites) == 2
    assert sum(s.share for s in plan.sites) == pytest.approx(1.0)
    left, right = sorted(plan.sites, key=lambda s: s.x)
    assert left.x < 0.5 < right.x
    assert left.owner is None and right.owner is None


def test_the_saved_plans_load_back_the_same(catalog: Catalog, tmp_path: Path) -> None:
    stats = mine_territories(catalog, 0, [_map(catalog)], [{}], [2])
    save_territories(tmp_path, {0: stats})
    assert load_territories(tmp_path)[0].plans_by_map == stats.plans_by_map

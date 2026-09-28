"""Tests for one level's border guarding."""

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.segment import label_zones
from vcmi_mapgen.core.model import PlacedObject, Tile, Zone
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.planning.entrances import plan_entrances
from vcmi_mapgen.core.planning.zone_index import ZoneRecord
from vcmi_mapgen.core.steps.border.crossings import LevelGrid
from vcmi_mapgen.core.steps.border.guard import BorderLevel, guard_level

S, GRASS = 20, 2


def _level(loot: bool) -> BorderLevel:
    ts1 = frozenset((x, y) for x in range(10) for y in range(S))
    ts2 = frozenset((x, y) for x in range(10, S) for y in range(S))
    zones = {
        zid: Zone(Terrain(GRASS), len(ts), (sum(x for x, _ in ts) / len(ts), 9.5), sorted(ts), ts)
        for zid, ts in ((1, ts1), (2, ts2))
    }
    records = [
        ZoneRecord(1, "grass", ts1, ts1, ts1, loot_zone=loot),
        ZoneRecord(2, "grass", ts2, ts2, ts2, loot_zone=loot),
    ]
    grid = LevelGrid(S, S, [[GRASS] * S for _ in range(S)], zones)
    return BorderLevel(
        grid, plan_entrances(label_zones(zones)), records, frozenset(), frozenset[Tile]()
    )


def test_guard_level_is_deterministic_and_leaves_its_input(catalog: Catalog) -> None:
    lv = _level(loot=False)
    before: list[PlacedObject] = []
    guarded = guard_level(catalog, lv, before, 3)
    assert guarded == guard_level(catalog, lv, before, 3)
    assert before == []
    assert guarded.guard_tiles
    assert {(o.x, o.y) for o in guarded.objs} <= guarded.guard_tiles


def test_loot_zones_get_no_guard(catalog: Catalog) -> None:
    guarded = guard_level(catalog, _level(loot=True), [], 3)
    assert not guarded.objs
    assert not guarded.guard_tiles

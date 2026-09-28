"""Tests for the zone records and walk targets gating leaves behind."""

from vcmi_mapgen.core.model import Footprint, PlacedObject, Role, Tile
from vcmi_mapgen.core.planning.zone_index import ZoneRecord
from vcmi_mapgen.core.steps.gated.loot_zones import mark_loot_zones, walk_targets


def _record(zid: int, x0: int) -> ZoneRecord:
    ts = frozenset((x, y) for x in range(x0, x0 + 4) for y in range(4))
    return ZoneRecord(zid, "grass", ts, ts, ts)


def _obj(t: Tile, purpose: str) -> PlacedObject:
    return PlacedObject(t[0], t[1], 0, purpose, "thing", Footprint.one(Role.VISIT))


def test_only_sealed_zones_become_loot_zones() -> None:
    records = [_record(1, 0), _record(2, 4)]
    marked = mark_loot_zones(records, {2})
    assert [zr.loot_zone for zr in marked] == [False, True]
    assert marked[0] is records[0]


def test_walk_targets_add_purposeful_objects_and_drop_sealed_tiles() -> None:
    records = [_record(1, 0), _record(2, 4)]
    new = [_obj((1, 1), "GATE"), _obj((2, 2), ""), _obj((5, 1), "KEY")]
    targets = walk_targets([(0, 0), (6, 3)], new, records, {2})
    assert targets == [(0, 0), (1, 1)]

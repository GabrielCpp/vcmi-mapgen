"""Tests for one level's scatter."""

from dataclasses import replace

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.segment import label_zones
from vcmi_mapgen.core.model import Tile, Zone
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.placement.site import PlacedZone
from vcmi_mapgen.core.planning.zone_index import ZoneRecord
from vcmi_mapgen.core.planning.zone_plan import PlanLevel, PlanZone
from vcmi_mapgen.core.steps.scatter.piles import PileLevel, scatter_level


def _level() -> PileLevel:
    ts = frozenset((x, y) for x in range(30) for y in range(24))
    zone = Zone(Terrain.GRASS, len(ts), (14.5, 11.5), sorted(ts), ts)
    none = frozenset[Tile]()
    return PileLevel(
        1,
        [ZoneRecord(1, "grass", ts, ts, ts, ts)],
        PlanLevel({1: PlanZone("grass", ts, (), none, none, none)}, {}),
        {1: PlacedZone((), none, (), ts, ts, none)},
        label_zones({1: zone}),
        none,
    )


def test_scatter_level_places_piles_on_its_level(catalog: Catalog) -> None:
    lv = _level()
    piles = scatter_level(catalog, lv, [], 3, 30)
    assert piles.objs
    assert all(o.level == 1 for o in piles.objs)
    assert len(piles.log) == 1
    assert [(o.x, o.y, o.kind) for o in scatter_level(catalog, lv, [], 3, 30).objs] == [
        (o.x, o.y, o.kind) for o in piles.objs
    ]


def test_a_loot_zone_gets_no_piles(catalog: Catalog) -> None:
    lv = _level()
    lv = replace(lv, records=[replace(zr, loot_zone=True) for zr in lv.records])
    assert scatter_level(catalog, lv, [], 3, 30) == scatter_level(catalog, lv, [], 4, 30)
    assert not scatter_level(catalog, lv, [], 3, 30).objs

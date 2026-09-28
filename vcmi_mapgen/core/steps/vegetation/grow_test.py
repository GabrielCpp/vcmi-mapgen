"""Tests for one level's vegetation growth."""

from dataclasses import replace

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.segment import label_zones
from vcmi_mapgen.core.model import Tile, Zone
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.planning.zone_plan import PlanLevel, PlanZone, ZonePlan
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.steps.vegetation.grow import GrowLevel, grow_level, vegetation_models
from vcmi_mapgen.core.steps.vegetation.result import VegetatedZone


def _level(taken: frozenset[Tile]) -> GrowLevel:
    ts = frozenset((x, y) for x in range(24) for y in range(20))
    zone = Zone(Terrain.GRASS, len(ts), (11.5, 9.5), sorted(ts), ts)
    none = frozenset[Tile]()
    web = frozenset(t for t in ts if t[0] == 12 or t[1] == 10)
    plan = PlanLevel({1: PlanZone("grass", ts, (), web, none, none)}, {})
    return GrowLevel(0, plan, {1: zone.centroid}, label_zones({1: zone}), taken)


def test_grow_level_is_deterministic_and_keeps_off_taken_tiles(
    catalog: Catalog, priors: Priors
) -> None:
    taken = frozenset((x, y) for x in range(24) for y in range(4))
    lv = _level(taken)
    models = vegetation_models(catalog, priors.vegetation, ZonePlan({0: lv.plan}, ()))
    grown = grow_level(models, lv, 5)
    assert grown.objs
    assert [(o.x, o.y, o.kind) for o in grow_level(models, lv, 5).objs] == [
        (o.x, o.y, o.kind) for o in grown.objs
    ]
    assert not {(o.x, o.y) for o in grown.objs} & taken
    assert grown.zones[1].open_set <= grown.zones[1].passable


def test_a_terrain_without_categories_grows_nothing(catalog: Catalog, priors: Priors) -> None:
    lv = _level(frozenset())
    models = vegetation_models(catalog, priors.vegetation, ZonePlan({0: lv.plan}, ()))
    models = {t: replace(m, cats=[]) for t, m in models.items()}
    grown = grow_level(models, lv, 5)
    assert grown == grow_level(models, lv, 5)
    assert not grown.objs
    assert grown.zones == {1: VegetatedZone()}

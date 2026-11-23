from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.placement.site import LevelField, SiteZone, ZoneSite
from vcmi_mapgen.core.priors.gameplay import TerrainStats
from vcmi_mapgen.core.reading.families import mine_family
from vcmi_mapgen.core.reading.supply import town_supply
from vcmi_mapgen.core.steps.gameplay.allocate import site_variants
from vcmi_mapgen.core.steps.gameplay.conftest import TownAt
from vcmi_mapgen.core.steps.gameplay.supply import stand_pairs

_ST = TerrainStats(0, {}, {}, {}, {}, {}, [], [], [], 0.0, {})


def _site(catalog: Catalog, w: int, h: int) -> ZoneSite:
    grid = [[int(Terrain.GRASS)] * w for _ in range(h)]
    ts = frozenset((x, y) for x in range(w) for y in range(h))
    zone = SiteZone("grass", _ST, ts, frozenset(), frozenset({(0, 0)}), ts, ts)
    return ZoneSite(catalog, 1, zone, LevelField.build(0, grid, []), 3)


def test_every_town_stands_its_own_pair_near_it(catalog: Catalog, town_at: TownAt) -> None:
    site = _site(catalog, 64, 24)
    towns = [town_at(8, 12), town_at(56, 12)]
    stood = stand_pairs([site], site_variants(catalog), towns)
    assert [f for f, _o in stood] == [mine_family(r) for r in ("sawmill", "orePit")] * 2
    assert [s.gaps() for s in town_supply(catalog, [*towns, *site.objs])] == [[], []]


def test_a_town_with_no_room_goes_without(catalog: Catalog, town_at: TownAt) -> None:
    site = _site(catalog, 64, 24)
    assert stand_pairs([site], site_variants(catalog), [town_at(8, 60)]) == []

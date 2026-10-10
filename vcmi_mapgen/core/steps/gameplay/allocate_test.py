from collections.abc import Mapping

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.placement.site import LevelField, SiteZone, ZoneSite
from vcmi_mapgen.core.priors.gameplay import TerrainStats
from vcmi_mapgen.core.reading.effort import effort_map
from vcmi_mapgen.core.reading.effort_test import TOLL, grid_route
from vcmi_mapgen.core.reading.mines import BASIC_MINE_RES
from vcmi_mapgen.core.reading.routes import Spot
from vcmi_mapgen.core.steps.gameplay.allocate import (
    Days,
    Offer,
    Pricer,
    Survey,
    keep_promise,
    rank,
    site_variants,
)

_ST = TerrainStats(0, {}, {}, {}, {}, {}, [], [], [], 0.0, {})
_SIDE = 24


def _site(catalog: Catalog) -> ZoneSite:
    grid = [[int(Terrain.GRASS)] * _SIDE for _ in range(_SIDE)]
    ts = frozenset((x, y) for x in range(_SIDE) for y in range(_SIDE))
    zone = SiteZone("grass", _ST, ts, frozenset(), frozenset({(0, 0)}), ts, ts)
    return ZoneSite(catalog, 1, zone, LevelField.build(0, grid, []), 3)


def _offer(site: ZoneSite, catalog: Catalog, days: Days) -> Offer:
    ident = site_variants(catalog)(site, "gemPond")[0]
    return Offer(site, ident, (5, 5), days)


def test_the_rare_offer_serving_more_waiting_players_wins(catalog: Catalog) -> None:
    site = _site(catalog)
    one, both = _offer(site, catalog, (10, None)), _offer(site, catalog, (12, 12))
    best: Days = (None, None)
    assert rank(both, best, "gemPond") < rank(one, best, "gemPond")


def test_the_rare_offer_keeping_the_gap_wins(catalog: Catalog) -> None:
    site = _site(catalog)
    wide, even = _offer(site, catalog, (5, 12)), _offer(site, catalog, (10, 12))
    best: Days = (None, None)
    assert rank(even, best, "gemPond") < rank(wide, best, "gemPond")


def test_a_wood_offer_serves_its_own_player(catalog: Catalog) -> None:
    site = _site(catalog)
    near_first, near_second = _offer(site, catalog, (3, 9)), _offer(site, catalog, (9, 4))
    best: Days = (None, None)
    assert rank(near_second, best, "sawmill", 1) < rank(near_first, best, "sawmill", 1)


def _survey(missing: str, calls: list[int]) -> Survey:
    route = grid_route(["." * _SIDE] * _SIDE)
    maps = [effort_map(route, [h], TOLL) for h in (Spot(0, 0, 0), Spot(0, _SIDE - 1, 0))]
    have: Mapping[str, Days] = {r: (None, None) if r == missing else (4, 4) for r in BASIC_MINE_RES}

    def survey() -> tuple[Pricer, Mapping[str, Days]]:
        calls.append(1)
        return Pricer(maps), have

    return survey


def _mines(site: ZoneSite) -> int:
    return sum(1 for o in site.objs if o.purpose == Purpose.MINE)


def test_one_rare_mine_serves_both_players(catalog: Catalog) -> None:
    site, calls = _site(catalog), list[int]()
    kept = keep_promise([site], site_variants(catalog), _survey("gemPond", calls))
    assert kept.warnings == ()
    assert _mines(site) == 1
    assert len(calls) == 2


def test_each_player_gets_its_own_wood_mine(catalog: Catalog) -> None:
    site, calls = _site(catalog), list[int]()
    kept = keep_promise([site], site_variants(catalog), _survey("sawmill", calls))
    assert kept.warnings == ()
    assert _mines(site) == 2

import random
from collections.abc import Iterable, Mapping
from typing import override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.placement.guard_draw import GuardDraw
from vcmi_mapgen.core.placement.site import LevelField, SiteZone, ZoneSite
from vcmi_mapgen.core.priors.counts import CountCurve, FamilyCurves, FamilyFit
from vcmi_mapgen.core.priors.gameplay import TerrainStats
from vcmi_mapgen.core.reading.effort import effort_map
from vcmi_mapgen.core.reading.effort_test import TOLL, grid_route
from vcmi_mapgen.core.reading.families import mine_family
from vcmi_mapgen.core.reading.mines import BASIC_MINE_RES
from vcmi_mapgen.core.reading.routes import Spot
from vcmi_mapgen.core.steps.gameplay.allocate import (
    Days,
    Offer,
    Pricer,
    Survey,
    _pick,  # pyright: ignore[reportPrivateUsage]
    _stand,  # pyright: ignore[reportPrivateUsage]
    drawn_guard,
    keep_promise,
    keeps_even,
    offers,
    promised_guard,
    prune,
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


def test_a_wood_offer_serves_its_own_player(catalog: Catalog) -> None:
    site = _site(catalog)
    near_first, near_second = _offer(site, catalog, (3, 9)), _offer(site, catalog, (9, 4))
    best: Days = (None, None)
    assert rank(near_second, best, 1) < rank(near_first, best, 1)


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


class _Flat(Pricer):
    flat: Days = (3, 14)

    @override
    def days(self, spot: Spot, level: int, shut: frozenset[Spot]) -> Days:
        return self.flat

    @override
    def prime(self, level: int, wants: Iterable[tuple[Spot, frozenset[Spot]]]) -> None:
        return None


def _rare_survey(site: ZoneSite, missing: tuple[str, ...], stood: int, days: Days) -> Survey:
    def survey() -> tuple[Pricer, Mapping[str, Days]]:
        pricer = _Flat([])
        pricer.flat = days
        done = _mines(site) >= stood
        have: Mapping[str, Days] = {
            r: days if done and r in missing else (None, None) if r in missing else (4, 4)
            for r in BASIC_MINE_RES
        }
        return pricer, have

    return survey


def test_one_rare_mine_serves_both_players_whatever_their_gap(catalog: Catalog) -> None:
    site = _site(catalog)
    kept = keep_promise(
        [site], site_variants(catalog), _rare_survey(site, ("gemPond",), 1, (3, 14))
    )
    assert kept.warnings == ()
    assert _mines(site) == 1
    assert dict(kept.cover)["gemPond"] == 1


def test_a_pick_that_fails_to_stand_gives_way_to_the_next_offer(catalog: Catalog) -> None:
    site = _site(catalog)
    pool = list(offers([site], site_variants(catalog), _Flat([]), "gemPond", 3))
    top = _pick(pool, (None, None), set())
    assert top is not None
    assert not _stand(top, 3)
    survey = _rare_survey(site, ("gemPond",), 1, (3, 14))
    kept = keep_promise([site], site_variants(catalog), survey)
    assert kept.warnings == ()
    assert [o.anchor for o in kept.stood] != [top.anchor]
    assert _mines(site) == 1


def test_two_rare_resources_stand_on_disjoint_cells(catalog: Catalog) -> None:
    site = _site(catalog)
    missing = ("gemPond", "crystalCavern")
    kept = keep_promise([site], site_variants(catalog), _rare_survey(site, missing, 2, (3, 14)))
    assert kept.warnings == ()
    first, second = kept.stood
    assert first.cells.isdisjoint(second.cells)
    assert first.anchor != second.anchor


def test_the_prune_drops_a_pick_a_later_pick_reaches_in_time(catalog: Catalog) -> None:
    site = _site(catalog)
    early, late = _offer(site, catalog, (10, 10, None)), _offer(site, catalog, (12, 12, 12))
    assert prune([early, late], (None, None, None)) == [late]


def test_the_prune_keeps_picks_that_each_reach_a_player_alone(catalog: Catalog) -> None:
    site = _site(catalog)
    left, right = _offer(site, catalog, (10, None)), _offer(site, catalog, (None, 12))
    assert prune([left, right], (None, None)) == [left, right]


def test_a_player_no_spot_reaches_in_time_is_named_and_gets_no_mine(catalog: Catalog) -> None:
    site = _site(catalog)
    kept = keep_promise(
        [site], site_variants(catalog), _rare_survey(site, ("gemPond",), 1, (3, 30))
    )
    assert any("gemPond" in w and "[1]" in w for w in kept.warnings)
    assert _mines(site) == 1


def test_each_player_gets_its_own_wood_mine(catalog: Catalog) -> None:
    site, calls = _site(catalog), list[int]()
    kept = keep_promise([site], site_variants(catalog), _survey("sawmill", calls))
    assert kept.warnings == ()
    assert _mines(site) == 2


def test_a_promised_mine_never_draws_past_its_promised_guard() -> None:
    record = FamilyFit(CountCurve(0.0, 1.0, 0.0), 0.0, (0.2, 0.0, 0.0, 0.0, 0.0, 0.8))
    curves = FamilyCurves(100, {mine_family(r): record for r in ("sawmill", "gold")})
    guarding = drawn_guard(GuardDraw(curves, 7), random.Random(3))
    for res in ("sawmill", "gold"):
        seen = {guarding(res) for _ in range(200)}
        assert seen == {0, promised_guard(res)}


def test_a_mine_that_opens_a_gap_does_not_keep_the_players_even() -> None:
    assert not keeps_even((11, 11), (1, 12))
    assert keeps_even((11, 11), (9, 20))


def test_a_mine_that_closes_a_gap_keeps_the_players_even() -> None:
    assert keeps_even((2, 11), (12, 5))

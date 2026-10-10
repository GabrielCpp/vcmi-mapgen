import random

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.placement.site import LevelField, SiteZone, ZoneSite, door_cells, spot
from vcmi_mapgen.core.priors.gameplay import TerrainStats
from vcmi_mapgen.core.reading.effort import Effort
from vcmi_mapgen.core.reading.paint import Accent
from vcmi_mapgen.core.reading.routes import Spot
from vcmi_mapgen.core.steps.gameplay.landmark import (
    KINDS,
    LANDMARK_FLOOR,
    TOP_TIER,
    PatchFooting,
    above_top_tier,
    dragon_order,
    kind_order,
    landmark_pool,
    place_dragon,
    place_landmarks,
)

_ST = TerrainStats(0, {}, {}, {}, {}, {}, [], [], [], 0.0, {})
_PATCH = frozenset((x, y) for x in range(5, 11) for y in range(5, 11))


def _site(catalog: Catalog) -> ZoneSite:
    """A 16x16 grass zone holding a 6x6 lava patch, reached from its corner."""
    grid = [
        [int(Terrain.LAVA if (x, y) in _PATCH else Terrain.GRASS) for x in range(16)]
        for y in range(16)
    ]
    ts = frozenset((x, y) for x in range(16) for y in range(16))
    zone = SiteZone("grass", _ST, ts, frozenset(), frozenset({(0, 0)}), ts, ts)
    return ZoneSite(catalog, 1, zone, LevelField.build(0, grid, []), 3)


def test_kind_order_leads_with_the_draw_and_keeps_the_rest_in_order() -> None:
    firsts = set[str]()
    for seed in range(200):
        order = kind_order(random.Random(seed))
        firsts.add(order[0].name)
        assert sorted(k.name for k in order) == sorted(k.name for k in KINDS)
        assert order[1:] == [k for k in KINDS if k != order[0]]
    assert firsts == {k.name for k in KINDS}


def test_every_kind_has_a_pool_on_lava(catalog: Catalog) -> None:
    assert all(landmark_pool(catalog, kind, "lava") for kind in KINDS)


def test_patch_footing_keeps_every_door_on_the_patch(catalog: Catalog) -> None:
    site = _site(catalog)
    ident = landmark_pool(catalog, KINDS[2], "lava")[0]
    footing = PatchFooting(_PATCH)
    for anchor in sorted(site.ts):
        if spot(site, footing, ident, anchor) is not None:
            assert all(t in _PATCH for t in door_cells(ident.footprint, anchor))
    assert footing.fit(site, ident, (1, 1)) is None


def test_a_patch_at_the_floor_takes_one_landmark_on_it(catalog: Catalog) -> None:
    site = _site(catalog)
    patch = Accent(1, Terrain.LAVA, _PATCH)
    assert place_landmarks(site, [patch], 7) == 1
    landmark = site.objs[0]
    doors = door_cells(landmark.footprint, (landmark.x, landmark.y))
    assert doors
    assert all(t in _PATCH for t in doors)


def test_small_patches_and_other_zones_take_none(catalog: Catalog) -> None:
    site = _site(catalog)
    small = frozenset(sorted(_PATCH)[: LANDMARK_FLOOR - 1])
    patches = [Accent(1, Terrain.LAVA, small), Accent(2, Terrain.LAVA, _PATCH)]
    assert place_landmarks(site, patches, 7) == 0


def test_no_ordinary_pool_holds_a_dragon_dwelling(catalog: Catalog) -> None:
    for kind in KINDS:
        assert not any(above_top_tier(catalog, i) for i in landmark_pool(catalog, kind, "lava"))


def test_the_dragon_tries_the_patches_the_homes_reach_last_first() -> None:
    near = Accent(1, Terrain.LAVA, frozenset((x, 0) for x in range(30)))
    far = Accent(2, Terrain.SNOW, frozenset((x, 9) for x in range(20)))
    small = Accent(3, Terrain.SAND, frozenset((x, 20) for x in range(LANDMARK_FLOOR - 1)))

    def effort(spot: Spot) -> Effort | None:
        return Effort(spot.y, 0, spot.y + spot.x)

    assert dragon_order({0: [near, far, small]}, effort) == [(0, far), (0, near)]
    assert dragon_order({0: [near], 1: [far]}, lambda s: None) == []


def test_the_dragon_patch_takes_a_dragon_behind_a_top_guard(catalog: Catalog) -> None:
    site = _site(catalog)
    patch = Accent(1, Terrain.LAVA, _PATCH)
    assert place_dragon({(0, 1): site}, [(0, patch)], 7) == (0, patch)
    assert place_landmarks(site, [patch], 7, patch) == 0
    dwelling = next(o for o in site.objs if o.purpose == Purpose.DWELLING)
    assert (catalog.dwelling_level(dwelling.kind) or 0) > TOP_TIER
    guards = [o for o in site.objs if o.purpose == Purpose.GUARD]
    assert [g.kind for g in guards] == [catalog.guard(TOP_TIER).kind]

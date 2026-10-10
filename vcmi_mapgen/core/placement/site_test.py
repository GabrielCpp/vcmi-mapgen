from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Footprint, Identity, PlacedObject, Role
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.placement.site import (
    LevelField,
    SidedFooting,
    SiteZone,
    TownFooting,
    ZoneFooting,
    ZoneSite,
)
from vcmi_mapgen.core.priors.gameplay import TerrainStats

_TOWN = Identity(
    "town",
    "castle",
    "castle",
    Footprint(
        3,
        2,
        (
            (-2, -1, Role.BLOCKING),
            (-1, -1, Role.BLOCKING),
            (0, -1, Role.BLOCKING),
            (-2, 0, Role.BLOCKING),
            (-1, 0, Role.ENTRANCE),
            (0, 0, Role.BLOCKING),
        ),
    ),
)
_TALL = Identity(
    "town",
    "castle",
    "castle",
    Footprint(
        3,
        3,
        (
            *_TOWN.footprint.cells,
            (-2, -2, Role.OVERLAY),
            (-1, -2, Role.OVERLAY),
            (0, -2, Role.OVERLAY),
        ),
    ),
)
_ROCK = Identity("rock", "rock", "rock", Footprint(1, 1, ((0, 0, Role.BLOCKING),)))
_ST = TerrainStats(0, {}, {}, {}, {}, {}, [], [], [], 0.0, {})


def _site(catalog: Catalog, outside: Terrain, vegetated: bool) -> ZoneSite:
    """A 10x10 zone at the left of a 12x10 level whose two right columns are ``outside``,
    covered by trees when ``vegetated``."""
    grid = [[int(Terrain.GRASS)] * 10 + [int(outside)] * 2 for _ in range(10)]
    tree = Footprint(1, 1, ((0, 0, Role.BLOCKING),))
    objs = (
        [PlacedObject(x, y, 0, "", "tree", tree) for x in (10, 11) for y in range(10)]
        if vegetated
        else []
    )
    ts = frozenset((x, y) for x in range(10) for y in range(10))
    zone = SiteZone("grass", _ST, ts, frozenset(), frozenset({(0, 0)}), ts, ts)
    return ZoneSite(catalog, 1, zone, LevelField.build(0, grid, objs), 3)


def _open_top(catalog: Catalog) -> ZoneSite:
    """A zone over rows 3 to 9 of a 12x10 open grass level: rows 0 to 2 lie outside it."""
    grid = [[int(Terrain.GRASS)] * 12 for _ in range(10)]
    ts = frozenset((x, y) for x in range(12) for y in range(3, 10))
    zone = SiteZone("grass", _ST, ts, frozenset(), frozenset({(0, 9)}), ts, ts)
    return ZoneSite(catalog, 1, zone, LevelField.build(0, grid, []), 3)


def test_a_town_may_spill_onto_vegetation_outside_its_zone(catalog: Catalog) -> None:
    site = _site(catalog, Terrain.GRASS, vegetated=True)
    assert TownFooting().fit(site, _TOWN, (10, 5)) is not None


def test_a_town_never_spills_onto_water(catalog: Catalog) -> None:
    site = _site(catalog, Terrain.WATER, vegetated=False)
    assert TownFooting().fit(site, _TOWN, (10, 5)) is None


def test_a_town_never_spills_onto_open_land_outside_its_zone(catalog: Catalog) -> None:
    site = _site(catalog, Terrain.GRASS, vegetated=False)
    assert TownFooting().fit(site, _TOWN, (10, 5)) is None


def test_a_town_approach_stays_inside_its_zone(catalog: Catalog) -> None:
    site = _site(catalog, Terrain.GRASS, vegetated=True)
    assert TownFooting().fit(site, _TOWN, (10, 9)) is None


def test_zone_footing_keeps_the_body_inside_the_zone(catalog: Catalog) -> None:
    site = _site(catalog, Terrain.GRASS, vegetated=True)
    assert ZoneFooting().fit(site, _TOWN, (10, 5)) is None


def test_town_anchors_reach_past_the_zone_by_the_footprint(catalog: Catalog) -> None:
    site = _site(catalog, Terrain.GRASS, vegetated=True)
    assert TownFooting().admits(site, _TOWN, (11, 10))
    assert not TownFooting().admits(site, _TOWN, (12, 5))


def test_a_home_town_overlay_may_lie_on_open_land_outside_its_zone(catalog: Catalog) -> None:
    site = _open_top(catalog)
    assert TownFooting().fit(site, _TALL, (5, 4)) is None
    assert TownFooting(loose_overlay=True).fit(site, _TALL, (5, 4)) is not None


def test_a_home_town_body_still_stays_on_its_zone_or_vegetation(catalog: Catalog) -> None:
    site = _open_top(catalog)
    assert TownFooting(loose_overlay=True).fit(site, _TALL, (5, 3)) is None


def test_sided_footing_keeps_the_spots_beside_a_closed_tile(catalog: Catalog) -> None:
    site = _site(catalog, Terrain.GRASS, vegetated=True)
    assert SidedFooting(ZoneFooting()).admits(site, _ROCK, (9, 5))
    assert not SidedFooting(ZoneFooting()).admits(site, _ROCK, (5, 5))

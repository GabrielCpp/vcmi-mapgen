import pytest

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import CoverIndex, MapState, PlacedObject, Tile, Zone
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.planning.pricing import (
    Opener,
    PrizeCount,
    UnreachedPlaceError,
    effort_with,
)
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.priors.effort import EffortPriors
from vcmi_mapgen.core.steps.portal import rescue as RS
from vcmi_mapgen.core.steps.portal.hoard import HoardPricing, fill_hoards

SIZE = 40
TOWN = "avctowx0"


def _zone(ts: frozenset[Tile]) -> Zone:
    cx = sum(x for x, _ in ts) / len(ts)
    cy = sum(y for _, y in ts) / len(ts)
    return Zone(Terrain.GRASS, len(ts), (cx, cy), sorted(ts), ts)


def _enclave() -> tuple[list[list[Terrain]], dict[int, Zone], frozenset[Tile]]:
    grid = [[Terrain.GRASS] * SIZE for _ in range(SIZE)]
    inner = frozenset((x, y) for x in range(31, 37) for y in range(31, 37))
    for y in range(28, SIZE):
        for x in range(28, SIZE):
            if (x, y) not in inner:
                grid[y][x] = Terrain.ROCK
    outer = frozenset(
        (x, y) for x in range(SIZE) for y in range(SIZE) if grid[y][x] == Terrain.GRASS
    )
    return grid, {1: _zone(outer - inner), 2: _zone(inner)}, inner


def _rescued(
    catalog: Catalog, priors: Priors
) -> tuple[RS.PortalWorld, list[RS.Rescued], PlacedObject, list[list[Terrain]]]:
    grid, zones, _inner = _enclave()
    town = PlacedObject.at(catalog.identity_of(TOWN), (6, 6), purpose=Purpose.TOWN)
    objs = {0: [town]}
    world = RS.PortalWorld(
        SIZE,
        {0: grid},
        {0: zones},
        objs,
        {0: [(6, 7)]},
        {0: []},
        {0: CoverIndex(objs[0])},
        priors.gameplay[0],
    )
    rescued = RS.rescue_unreachable_zones(catalog, world, RS.Departure((0, (6, 6))), seed=3)
    return world, rescued, town, grid


def test_a_portal_place_holds_band_prizes_behind_its_portal(
    catalog: Catalog, priors: Priors
) -> None:
    world, rescued, town, grid = _rescued(catalog, priors)
    inner = world.zones_by_level[0][2].tiles_set
    state = MapState(size=SIZE, terrain={0: grid}, objs=[town], player_towns=[town])
    effort = EffortPriors()
    em = effort_with(catalog, state, effort.toll, world.objs_by_level[0][1:])
    pricing = HoardPricing(em, effort, {0: PrizeCount()})
    place = fill_hoards(catalog, world, rescued, pricing, seed=3)[0][2]
    assert place.opener is Opener.PORTAL
    assert place.price.band == effort.band(place.price.effort.total)
    assert place.prizes
    assert all((o.x, o.y) in inner for o in place.prizes)
    assert all(o in world.objs_by_level[0] for o in place.prizes)


def test_a_portal_place_no_home_reaches_raises(catalog: Catalog, priors: Priors) -> None:
    world, rescued, _town, grid = _rescued(catalog, priors)
    state = MapState(size=SIZE, terrain={0: grid}, objs=[])
    effort = EffortPriors()
    em = effort_with(catalog, state, effort.toll, world.objs_by_level[0])
    pricing = HoardPricing(em, effort, {0: PrizeCount()})
    with pytest.raises(UnreachedPlaceError):
        _ = fill_hoards(catalog, world, rescued, pricing, seed=3)

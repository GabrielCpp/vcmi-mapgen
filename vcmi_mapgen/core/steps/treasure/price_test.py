import pytest

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState, PlacedObject
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.planning.pricing import UnreachedPlaceError, effort_with, homes
from vcmi_mapgen.core.priors.effort import EffortPriors
from vcmi_mapgen.core.steps.gated.result import LootAccess
from vcmi_mapgen.core.steps.treasure.price import price_places

SIZE = 24
TOWN = "avctowx0"


def _state(catalog: Catalog, wall_at: int | None = None) -> MapState:
    grid = [
        [Terrain.ROCK if x == wall_at else Terrain.GRASS for x in range(SIZE)] for _ in range(SIZE)
    ]
    town = PlacedObject.at(catalog.identity_of(TOWN), (6, 6), purpose=Purpose.UNKNOWN)
    return MapState(size=SIZE, terrain={0: grid}, objs=[town], player_towns=[town])


def _access(x: int, y: int) -> LootAccess:
    return LootAccess(entry=(x, y), footprint=frozenset({(x, y)}), interactive=frozenset({(x, y)}))


def test_homes_are_the_visit_tiles_of_the_player_towns(catalog: Catalog) -> None:
    state = _state(catalog)
    assert homes(state)
    assert all(s.level == 0 and abs(s.x - 6) <= 4 and abs(s.y - 6) <= 4 for s in homes(state))


def test_a_far_place_lands_in_a_higher_band_than_a_near_one(catalog: Catalog) -> None:
    effort = EffortPriors(edges=(1, 2, 3))
    em = effort_with(catalog, _state(catalog), effort.toll)
    prices = price_places(em, {0: {1: _access(7, 8), 2: _access(22, 22)}}, effort)
    near, far = prices[0][1], prices[0][2]
    assert near.effort.guard == far.effort.guard == 0
    assert near.band < far.band
    assert far.effort.days > near.effort.days


def test_a_place_no_home_reaches_is_a_failure(catalog: Catalog) -> None:
    with pytest.raises(UnreachedPlaceError):
        em = effort_with(catalog, _state(catalog, wall_at=12), EffortPriors().toll)
        _ = price_places(em, {0: {1: _access(20, 20)}}, EffortPriors())

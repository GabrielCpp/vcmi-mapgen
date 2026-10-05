from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Identity, PlacedObject
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.reading.effort import effort_map
from vcmi_mapgen.core.reading.effort_test import TOLL, grid_route
from vcmi_mapgen.core.reading.promise import Promise, promise_from, promise_ways
from vcmi_mapgen.core.reading.routes import Spot

_RES = ("sawmill", "gemPond")


def _sawmill(catalog: Catalog, x: int, y: int) -> PlacedObject:
    ident: Identity = catalog.mines_by_resource("grass")["sawmill"][0]
    return PlacedObject(x, y, 0, Purpose.MINE, ident.kind, ident.footprint)


def test_a_late_player_and_a_wide_gap_break_the_promise() -> None:
    promise = Promise(({"sawmill": 4, "gemPond": 15}, {"sawmill": 9, "gemPond": 12}))
    assert promise.broken() == ["player 0 gemPond: 15 days", "sawmill: gap 5 days"]


def test_an_unreached_resource_breaks_the_promise() -> None:
    promise = Promise(({"gemPond": None},))
    assert promise.broken() == ["player 0 gemPond: None days"]
    assert promise.gap("gemPond") is None


def test_the_nearest_mine_counts(catalog: Catalog) -> None:
    em = effort_map(grid_route(["." * 40] * 8), [Spot(0, 0, 0)], TOLL)
    mines = [_sawmill(catalog, 36, 4), _sawmill(catalog, 10, 4)]
    assert promise_from(catalog, mines, [em], _RES).days == ({"sawmill": 1, "gemPond": None},)


def test_the_way_leads_to_the_nearest_mine(catalog: Catalog) -> None:
    em = effort_map(grid_route(["." * 40] * 8), [Spot(0, 0, 0)], TOLL)
    mines = [_sawmill(catalog, 36, 4), _sawmill(catalog, 10, 4)]
    ways = promise_ways(catalog, mines, [em], _RES)
    assert (0, 0) in ways[0]
    assert max(x for x, _y in ways[0]) <= 10

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import PlacedObject
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.reading.supply import entrance, supply_gaps, town_supply


def _town(catalog: Catalog, x: int, y: int, level: int = 0) -> PlacedObject:
    ident = catalog.candidates(Purpose.TOWN, "grass")[0]
    return PlacedObject(x, y, level, Purpose.TOWN, ident.kind, ident.footprint)


def _mine(catalog: Catalog, res: str, x: int, y: int, level: int = 0) -> PlacedObject:
    ident = catalog.mines_by_resource("grass")[res][0]
    return PlacedObject(x, y, level, Purpose.MINE, ident.kind, ident.footprint)


def test_the_supply_counts_tiles_between_entrances(catalog: Catalog) -> None:
    town = _town(catalog, 10, 10)
    mill = _mine(catalog, "sawmill", 20, 10)
    tx, ty = entrance(town)
    mx, my = entrance(mill)
    supply = town_supply(catalog, [town, mill])
    assert supply[0].nearest == {"sawmill": max(abs(tx - mx), abs(ty - my)), "orePit": None}


def test_a_mine_on_another_level_supplies_nothing(catalog: Catalog) -> None:
    objs = [_town(catalog, 10, 10), _mine(catalog, "sawmill", 12, 10, 1)]
    assert town_supply(catalog, objs)[0].nearest["sawmill"] is None


def test_a_far_or_missing_mine_is_a_gap(catalog: Catalog) -> None:
    objs = [
        _town(catalog, 10, 10),
        _mine(catalog, "sawmill", 40, 10),
        _mine(catalog, "orePit", 14, 10),
    ]
    assert supply_gaps(catalog, objs) == ["town at 10,10 level 0: no sawmill within 12 tiles"]

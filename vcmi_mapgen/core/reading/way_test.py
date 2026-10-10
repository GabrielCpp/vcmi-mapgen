from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import PlacedObject
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.reading.way import PlayerWay, close_share


def _mine(catalog: Catalog, res: str, x: int, y: int, level: int = 0) -> PlacedObject:
    ident = catalog.mines_by_resource("grass")[res][0]
    return PlacedObject(x, y, level, Purpose.MINE, ident.kind, ident.footprint)


def test_a_way_repeats_where_a_resource_comes_twice_before_all_were_met() -> None:
    way = PlayerWay(0, ((3, "gemPond"), (5, "gemPond"), (8, "sulfurDune")))
    assert way.repeat({"gemPond", "sulfurDune"}) == 1


def test_a_repeat_after_every_resource_was_met_is_no_repeat() -> None:
    way = PlayerWay(0, ((3, "gemPond"), (5, "sulfurDune"), (8, "gemPond")))
    assert way.repeat({"gemPond", "sulfurDune"}) is None


def test_the_close_share_counts_mines_of_one_resource_on_one_level(catalog: Catalog) -> None:
    objs = [
        _mine(catalog, "gemPond", 10, 10),
        _mine(catalog, "gemPond", 15, 10),
        _mine(catalog, "gemPond", 15, 10, 1),
        _mine(catalog, "sulfurDune", 12, 10),
    ]
    assert close_share(catalog, objs) == 0.5


def test_a_map_without_rare_mines_has_no_close_share(catalog: Catalog) -> None:
    assert close_share(catalog, [_mine(catalog, "sawmill", 10, 10)]) == 0.0

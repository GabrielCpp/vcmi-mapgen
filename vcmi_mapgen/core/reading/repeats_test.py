from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import PlacedObject
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.reading.repeats import nearest_copies, repeat_share


def _visit(catalog: Catalog, x: int, y: int, level: int = 0, n: int = 0) -> PlacedObject:
    ident = catalog.candidates(Purpose.MANA, "grass")[n]
    return PlacedObject(x, y, level, Purpose.MANA, ident.kind, ident.footprint)


def test_each_repeated_visitable_counts_tiles_to_its_nearest_copy(catalog: Catalog) -> None:
    objs = [_visit(catalog, 10, 10), _visit(catalog, 14, 12), _visit(catalog, 30, 10)]
    assert nearest_copies(catalog, objs) == [4, 4, 16]


def test_a_copy_on_another_level_is_no_copy(catalog: Catalog) -> None:
    objs = [_visit(catalog, 10, 10), _visit(catalog, 11, 10, 1)]
    assert nearest_copies(catalog, objs) == []


def test_the_share_counts_the_gaps_within_reach() -> None:
    assert repeat_share([4, 4, 16], 6) == 2 / 3
    assert repeat_share([], 6) == 0.0

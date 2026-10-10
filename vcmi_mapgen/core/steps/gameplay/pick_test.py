import random

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import PlacedObject
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.steps.gameplay.pick import Picker


def _picker(catalog: Catalog, x: int, y: int) -> Picker:
    picker = Picker(catalog, random.Random(1))
    ident = catalog.candidates(Purpose.MANA, "grass")[0]
    picker.use(ident, PlacedObject(x, y, 0, Purpose.MANA, ident.kind, ident.footprint))
    return picker


def test_a_copy_counts_near_on_its_level_only(catalog: Catalog) -> None:
    picker = _picker(catalog, 10, 10)
    ident = catalog.candidates(Purpose.MANA, "grass")[0]
    assert picker.near(ident, (0, 18, 10)) == 1
    assert picker.near(ident, (0, 30, 10)) == 0
    assert picker.near(ident, (1, 10, 10)) == 0
    assert picker.near(ident, None) == 0


def test_the_centres_with_no_copy_near_come_first(catalog: Catalog) -> None:
    picker = _picker(catalog, 10, 10)
    ident = catalog.candidates(Purpose.MANA, "grass")[0]
    centres = [(11, 10), (40, 10), (12, 12), (50, 50)]
    assert picker.clear_first(ident, 0, centres) == [(40, 10), (50, 50), (11, 10), (12, 12)]

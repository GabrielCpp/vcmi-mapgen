import random

from vcmi_mapgen.core.catalog import Catalog, Trait
from vcmi_mapgen.core.model import PlacedObject
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.priors.gameplay import TerrainStats
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


def test_a_town_dwelling_stands_only_as_a_random_dwelling(catalog: Catalog) -> None:
    st = TerrainStats(0, {}, {}, {}, {}, {}, [], [], [], 0.0, {})
    randoms = catalog.types_with(Trait.RANDOM_DWELLING)
    picker = Picker(catalog, random.Random(3))
    picked = [
        p.ident
        for _ in range(40)
        for terrain in ("grass", "dirt", "snow", "lava", "subterra")
        for level in range(1, 8)
        if (p := picker.pick(f"{Purpose.DWELLING}:{level}", terrain, st)) is not None
    ]
    fixed = [i for i in picked if i.type not in randoms]
    assert fixed, "neutral dwellings still stand fixed"
    assert all(catalog.dwelling_faction(i.kind) is None for i in fixed)

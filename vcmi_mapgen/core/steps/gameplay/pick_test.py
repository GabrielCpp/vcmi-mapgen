import math
import random

from vcmi_mapgen.core.catalog import Catalog, Trait
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.priors.gameplay import TerrainStats
from vcmi_mapgen.core.reading.families import dwelling_family, mine_family
from vcmi_mapgen.core.reading.repeats import kind_of
from vcmi_mapgen.core.steps.gameplay.pick import RANDOM_DWELLING_SHARE, Picker


def _stats() -> TerrainStats:
    return TerrainStats(0, {}, {}, {}, {}, {}, [], [], [], 0.0, {})


def test_the_chances_of_the_kinds_sum_to_one(catalog: Catalog) -> None:
    picker = Picker(catalog, random.Random(1))
    for family in (
        Purpose.MANA,
        mine_family("sawmill"),
        dwelling_family(0),
        dwelling_family(3),
    ):
        got = picker.kinds(family, "grass", _stats())
        assert got, family
        assert math.isclose(sum(got.values()), 1.0)


def test_a_random_dwelling_takes_its_share_of_the_kinds(catalog: Catalog) -> None:
    picker = Picker(catalog, random.Random(1))
    rand = kind_of(catalog.random_dwelling(3))
    got = picker.kinds(dwelling_family(3), "grass", _stats())
    assert math.isclose(got[rand], RANDOM_DWELLING_SHARE)
    assert picker.kinds(dwelling_family(0), "grass", _stats()) == {
        kind_of(catalog.random_dwelling(None)): 1.0
    }


def test_a_pick_of_a_kind_draws_only_that_kind(catalog: Catalog) -> None:
    picker = Picker(catalog, random.Random(2))
    st = _stats()
    for family in (Purpose.MANA, mine_family("sawmill"), dwelling_family(2)):
        for kind in picker.kinds(family, "grass", st):
            for _ in range(8):
                picked = picker.pick(family, "grass", st, kind)
                assert picked is not None
                assert kind_of(picked.ident) == kind


def test_a_kind_the_terrain_does_not_offer_draws_nothing(catalog: Catalog) -> None:
    picker = Picker(catalog, random.Random(2))
    st = _stats()
    absent = ("noSuchType", "noSuchSubtype")
    assert picker.pick(Purpose.MANA, "grass", st, absent) is None
    assert not picker.offers(Purpose.MANA, "grass", st, absent)
    kind = next(iter(picker.kinds(Purpose.MANA, "grass", st)))
    assert picker.offers(Purpose.MANA, "grass", st, kind)


def test_a_pick_of_a_kind_keeps_the_whole_family_as_its_pool(catalog: Catalog) -> None:
    picker = Picker(catalog, random.Random(2))
    st = _stats()
    kinds = picker.kinds(Purpose.BONUS_TEMP, "grass", st)
    assert len(kinds) > 1
    picked = picker.pick(Purpose.BONUS_TEMP, "grass", st, next(iter(kinds)))
    assert picked is not None
    assert {kind_of(i) for i in picked.pool} == set(kinds)


def test_a_town_dwelling_stands_only_as_a_random_dwelling(catalog: Catalog) -> None:
    st = _stats()
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

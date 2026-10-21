import random
from types import SimpleNamespace
from typing import cast

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import PlacedObject
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement.site import ZoneSite
from vcmi_mapgen.core.priors.gameplay import TerrainStats
from vcmi_mapgen.core.reading.families import dwelling_family
from vcmi_mapgen.core.reading.repeats import kind_of
from vcmi_mapgen.core.steps.gameplay.bands import Slot
from vcmi_mapgen.core.steps.gameplay.pick import Picker
from vcmi_mapgen.core.steps.gameplay.roster import roster


def _sites(*terrains: str) -> list[ZoneSite]:
    st = TerrainStats(0, {}, {}, {}, {}, {}, [], [], [], 0.0, {})
    return [
        cast(
            ZoneSite,
            cast(
                object,
                SimpleNamespace(
                    ts=[(x, 0) for x in range(10)], zone=SimpleNamespace(terrain=t), st=st
                ),
            ),
        )
        for t in terrains
    ]


def _slots() -> list[Slot]:
    return [Slot(Purpose.BONUS_TEMP)] * 12 + [Slot(dwelling_family(3), None, 1, 4)] * 4


def test_the_roster_is_the_same_for_a_seed(catalog: Catalog) -> None:
    sites = _sites("grass", "dirt")
    one = roster(Picker(catalog, random.Random(1)), sites, _slots(), random.Random(5))
    two = roster(Picker(catalog, random.Random(1)), sites, _slots(), random.Random(5))
    assert one == two
    assert all(s.kind is not None for s in one[0])


def test_a_slot_keeps_its_place_and_its_fields(catalog: Catalog) -> None:
    slots = _slots()
    got, _counts = roster(
        Picker(catalog, random.Random(1)), _sites("grass"), slots, random.Random(5)
    )
    assert [(s.family, s.band, s.target) for s in got] == [
        (s.family, s.band, s.target) for s in slots
    ]


def test_a_kind_no_terrain_offers_is_never_drawn(catalog: Catalog) -> None:
    sites = _sites("grass")
    picker = Picker(catalog, random.Random(1))
    offered = set(picker.kinds(Purpose.BONUS_TEMP, "grass", sites[0].st))
    got, _counts = roster(picker, sites, [Slot(Purpose.BONUS_TEMP)] * 40, random.Random(2))
    assert {s.kind for s in got} <= offered


def test_a_slot_with_no_kind_on_any_site_keeps_none(catalog: Catalog) -> None:
    picker = Picker(catalog, random.Random(1))
    sites = _sites("subterra")
    assert picker.kinds(Purpose.MANA, "subterra", sites[0].st) == {}
    got, counts = roster(picker, sites, [Slot(Purpose.MANA)], random.Random(2))
    assert got[0].kind is None
    assert not counts


def test_the_counts_add_the_copies_standing_and_the_slots_drawn(catalog: Catalog) -> None:
    picker = Picker(catalog, random.Random(1))
    ident = catalog.candidates(Purpose.BONUS_TEMP, "grass")[0]
    picker.use(ident, PlacedObject(3, 3, 0, Purpose.BONUS_TEMP, ident.kind, ident.footprint))
    got, counts = roster(picker, _sites("grass"), [Slot(Purpose.BONUS_TEMP)] * 9, random.Random(2))
    kinds = [s.kind for s in got]
    assert counts[kind_of(ident)] == 1 + kinds.count(kind_of(ident))
    assert sum(counts.values()) == 1 + len(kinds)

from vcmi_mapgen.conftest import find_install
from vcmi_mapgen.core.model import Role
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.vcmi.catalog import objects as ON
from vcmi_mapgen.vcmi.catalog.adapter import VcmiCatalog
from vcmi_mapgen.vcmi.config import EMPTY_CONFIG, load_config
from vcmi_mapgen.vcmi.content.enabled import EnabledSet
from vcmi_mapgen.vcmi.content.mods_test import LAIR, TENT, fair_content


def test_the_base_game_bans_nothing() -> None:
    catalog = VcmiCatalog()
    assert "angel" in catalog.monsters(7)
    assert catalog.artifact("speculum") is not None


def test_a_ban_removes_a_name_from_every_list_it_appears_in() -> None:
    sets = VcmiCatalog().artifact_sets()
    part = sets[0].parts[0]
    catalog = VcmiCatalog(EnabledSet(banned=frozenset({"angel", "armageddon", part})))
    assert "angel" not in catalog.monsters(7)
    assert "armageddon" not in catalog.spells(4)
    assert catalog.artifact(part) is None
    assert all(part not in s.parts for s in catalog.artifact_sets())


def test_a_ban_by_object_type_empties_its_pools() -> None:
    boxes = [
        i
        for i in VcmiCatalog().candidates(Purpose.REWARD_PICKUP, "grass")
        if i.type == "pandoraBox"
    ]
    catalog = VcmiCatalog(EnabledSet(banned=frozenset({"pandoraBox"})))
    assert boxes and catalog.spec(boxes[0].kind) is None
    assert all(i.type != "pandoraBox" for i in catalog.candidates(Purpose.REWARD_PICKUP, "grass"))


def test_mod_objects_join_a_pool_after_the_base_games() -> None:
    catalog = VcmiCatalog(mods=fair_content())
    pool = catalog.candidates(Purpose.BANK, "sand")
    base = VcmiCatalog().candidates(Purpose.BANK, "sand")
    assert pool == [*base, fair_content().objects[LAIR].identity]
    assert TENT in [i.kind for i in catalog.candidates(Purpose.BANK, int(Terrain.GRASS))]
    assert catalog.identity_of(LAIR).type == "creatureBank"
    assert catalog.allowed_on(TENT, "grass") and not catalog.allowed_on(TENT, "sand")


def test_a_mod_object_has_a_spec_until_it_is_banned() -> None:
    spec = VcmiCatalog(mods=fair_content()).spec(LAIR)
    assert spec is not None and spec.purpose is Purpose.BANK and spec.blocking
    banned = VcmiCatalog(EnabledSet(banned=frozenset({LAIR})), fair_content())
    assert banned.spec(LAIR) is None
    assert LAIR not in [i.kind for i in banned.candidates(Purpose.BANK, "sand")]


def test_abandoned_mines_stand_on_their_terrain_and_respect_bans() -> None:
    mines = VcmiCatalog().abandoned_mines("lava")
    assert mines
    assert all(i.subtype in ("abandoned", "mine") for i in mines)
    banned = VcmiCatalog(EnabledSet(banned=frozenset({"mine"})))
    assert banned.abandoned_mines("lava") == []


def test_a_dragon_dwelling_reads_its_creature_level_unclamped() -> None:
    catalog = VcmiCatalog()
    assert catalog.dwelling_level("avgazur") == 10
    assert catalog.dwelling_level("avgfdrg") == 8
    assert catalog.dwelling_level("avgtrog0") == 1
    assert catalog.dwelling_level(catalog.random_dwelling(3).kind) is None


def test_a_fixed_monster_reads_its_creature_level_without_an_install() -> None:
    install = find_install()
    ON.use_config(EMPTY_CONFIG)
    try:
        catalog = VcmiCatalog()
        assert catalog.creature_level("AVWunic0") == 6
        assert catalog.creature_level("AVWddrx0") == 7
        assert catalog.creature_level("AVWbehl0") == 3
    finally:
        ON.use_config(load_config(install) if install is not None else EMPTY_CONFIG)


def test_a_pickup_or_a_monster_vanishes_and_a_sign_or_a_school_lasts() -> None:
    catalog = VcmiCatalog()
    assert catalog.is_vanish("avtgold0")
    assert catalog.is_vanish("avwmon3")
    assert catalog.is_vanish(catalog.random_artifact("minor").kind)
    assert not catalog.is_vanish("avxsndg0")
    assert not catalog.is_vanish("avsschm0")


def test_a_lasting_walk_on_object_visits_through_an_entrance() -> None:
    sign = VcmiCatalog().identity_of("avxsndg0")
    assert {role for _dx, _dy, role in sign.footprint.cells} == {Role.ENTRANCE}

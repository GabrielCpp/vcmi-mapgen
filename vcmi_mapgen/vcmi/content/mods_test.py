import json
from pathlib import Path

from vcmi_mapgen.core.model import Identity
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.vcmi.catalog import objects as OB
from vcmi_mapgen.vcmi.content.enabled import EnabledSet
from vcmi_mapgen.vcmi.content.manifest import ModManifest, read_manifests
from vcmi_mapgen.vcmi.content.mods import NO_MODS, ModContent, load_mods
from vcmi_mapgen.vcmi.content.objects import ModObject
from vcmi_mapgen.vcmi.footprint import footprint_of

LAIR = "fair/lair"
TENT = "fair/tent"


def _object(mod_id: str, kind: str, purpose: Purpose, terrains: frozenset[str] | None) -> ModObject:
    fp = footprint_of(("VV", "BX"))
    ident = Identity("creatureBank", kind.rpartition("/")[2], kind, fp)
    return ModObject(mod_id, ident, ("VV", "BA"), None, terrains, purpose, 900)


def fair_content() -> ModContent:
    manifests = {
        "fair": ModManifest("fair", name="Fair", version="1.0"),
        "fair.tents": ModManifest("fair.tents", name="Tents", version="0.2", parent="fair"),
    }
    lair = _object("fair", LAIR, Purpose.BANK, None)
    tent = _object("fair.tents", TENT, Purpose.BANK, frozenset({"grass"}))
    return ModContent(manifests, {LAIR: lair, TENT: tent})


def test_the_requirement_names_each_mod_an_object_comes_from_and_its_parents() -> None:
    content = fair_content()
    assert content.requirement(["avtgems0", "Fair/Tent"]) == [
        {"modId": "fair", "name": "Fair", "version": "1.0"},
        {"modId": "fair.tents", "name": "Tents", "parent": "fair", "version": "0.2"},
    ]
    assert content.requirement(["avtgems0"]) == []
    assert NO_MODS.requirement([LAIR]) == []


def test_a_pool_holds_the_templates_of_its_purpose_that_stand_on_the_terrain() -> None:
    content = fair_content()
    assert [i.kind for i in content.pool(Purpose.BANK, "grass")] == [LAIR, TENT]
    assert [i.kind for i in content.pool(Purpose.BANK, "sand")] == [LAIR]
    assert content.pool(Purpose.BANK, "water") == []
    assert content.pool(Purpose.MANA, "grass") == []


def test_a_template_the_base_game_holds_stays_the_base_games(tmp_path: Path) -> None:
    base = OB.gameplay_pool("grass", "TOWN")[0].kind
    templates = {
        "own": {"animation": "fair/own", "mask": ["A"]},
        "copy": {"animation": base, "mask": ["A"]},
    }
    config = {"core:creatureBank": {"types": {"lair": {"templates": templates}}}}
    folder = tmp_path / "Fair"
    (folder / "content" / "config").mkdir(parents=True)
    _ = (folder / "mod.json").write_text(json.dumps({"objects": ["config/fair"]}))
    _ = (folder / "content" / "config" / "fair.json").write_text(json.dumps(config))
    content = load_mods(read_manifests(tmp_path), EnabledSet(mods=frozenset({"fair"})))
    assert content.object("fair/own") is not None
    assert content.object(base) is None

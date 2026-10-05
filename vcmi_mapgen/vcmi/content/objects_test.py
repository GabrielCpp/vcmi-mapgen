import json
import zipfile
from pathlib import Path

from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.vcmi.content.manifest import read_manifests
from vcmi_mapgen.vcmi.content.objects import mod_objects

_TEMPLATE = {"animation": "fair/tent/AVtent", "mask": ["VV", "BA"]}
_CONFIG = {
    "core:creatureBank": {
        "types": {
            "lair": {
                "rmg": {"value": 2500},
                "templates": {"normal": {"animation": "fair/lair", "mask": ["VVV", "VBA"]}},
            },
        },
    },
    "fortuneTent": {
        "handler": "configurable",
        "base": {"rmg": {"value": 900}},
        "types": {
            "fortuneTent": {
                "rewards": [{"movePoints": 400}, {"secondary": {"luck": 1}}],
                "base": {"allowedTerrains": ["subterra", "grass"]},
                "templates": {"tent": _TEMPLATE, "copy": {**_TEMPLATE, "mask": ["A"]}},
            },
            "freeTent": {
                "rewards": [{"movePoints": 400}],
                "rmg": {"value": 0},
                "templates": {"free": {"animation": "fair/free", "mask": ["A"]}},
            },
        },
    },
    "statue": {
        "handler": "generic",
        "types": {"statue": {"templates": {"s": {"animation": "fair/statue", "mask": ["B"]}}}},
    },
}


def _fair(mods: Path) -> None:
    folder = mods / "Fair"
    folder.mkdir(parents=True)
    _ = (folder / "mod.json").write_text(json.dumps({"objects": ["config/fair"]}))
    with zipfile.ZipFile(folder / "content.zip", "w") as z:
        z.writestr("Config/Fair.json", "// objects\n" + json.dumps(_CONFIG))


def test_a_mod_config_yields_priced_objects_for_the_pools(tmp_path: Path) -> None:
    _fair(tmp_path)
    found = {o.identity.kind: o for o in mod_objects(read_manifests(tmp_path), {"fair"})}
    assert sorted(found) == ["fair/free", "fair/lair", "fair/statue", "fair/tent/AVtent"]
    lair, tent = found["fair/lair"], found["fair/tent/AVtent"]
    assert (lair.identity.type, lair.identity.subtype) == ("creatureBank", "lair")
    assert (lair.purpose, lair.price, lair.terrains) == (Purpose.BANK, 2500, None)
    assert (tent.purpose, tent.price) == (Purpose.SPELL_SKILL, 900)
    assert tent.terrains == frozenset({"subterr", "grass"})
    assert tent.stands_on("grass") and not tent.stands_on("sand")
    assert lair.stands_on("sand") and not lair.stands_on("water")


def test_an_object_with_no_price_or_no_reward_purpose_is_never_placed(tmp_path: Path) -> None:
    _fair(tmp_path)
    found = {o.identity.kind: o for o in mod_objects(read_manifests(tmp_path), {"fair"})}
    assert found["fair/free"].purpose is None
    assert found["fair/statue"].purpose is None


def test_a_disabled_mod_yields_nothing(tmp_path: Path) -> None:
    _fair(tmp_path)
    assert mod_objects(read_manifests(tmp_path), set()) == []

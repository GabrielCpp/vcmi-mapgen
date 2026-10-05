import json
from pathlib import Path

from vcmi_mapgen.core.model import JsonValue
from vcmi_mapgen.vcmi.config import VcmiConfig
from vcmi_mapgen.vcmi.content.manifest import MOD_FILE, ModManifest
from vcmi_mapgen.vcmi.content.map_format import (
    HOTA_FORMAT,
    NO_FORMAT,
    parse_map_format,
    read_map_format,
)

SECTION: dict[str, JsonValue] = {
    "supported": True,
    "objects": {
        "flotsam": [29, 0],
        "crackedIce": {"plain": [143, 4], "dark": [143, 4]},
        "seaChest": [82, 0],
    },
    "templates": {"hota/ice/Ice01.def": "HICE01.DEF"},
    "creatures": {"pirate": 151},
    "artifacts": {"pendant": 146},
}


def test_plain_and_struct_objects_name_their_class_and_subclass() -> None:
    fmt = parse_map_format(SECTION)
    assert fmt.objects[(29, 0)] == ("flotsam", "flotsam")
    assert fmt.objects[(143, 4)] == ("crackedIce", "plain")
    assert fmt.creatures == {151: "pirate"}


def test_a_template_animation_is_renamed_without_its_suffix_or_case() -> None:
    fmt = parse_map_format(SECTION)
    assert fmt.animation("hice01.def") == "hota/ice/Ice01"
    assert fmt.animation("AVTGEMS0.def") == "AVTGEMS0"
    assert NO_FORMAT.animation("avtgems0") == "avtgems0"


def test_the_format_wins_over_the_base_config() -> None:
    base = VcmiConfig(
        classes={82: ("seaChest", {0: "object"}), 54: ("monster", {})},
        creatures={151: "base"},
    )
    config = parse_map_format(SECTION).config(base)
    assert config.resolve(82, 0) == ("seaChest", "seaChest")
    assert config.resolve(29, 0) == ("flotsam", "flotsam")
    assert config.creatures[151] == "pirate"
    assert base.resolve(29, 0) is None


def _mod(root: Path, mod_id: str, doc: dict[str, JsonValue]) -> ModManifest:
    folder = root / mod_id
    folder.mkdir()
    _ = (folder / MOD_FILE).write_text(json.dumps(doc), encoding="utf-8")
    return ModManifest(mod_id, folder=folder)


def test_the_first_enabled_mod_that_supports_the_format_declares_it(tmp_path: Path) -> None:
    off: dict[str, JsonValue] = {"settings": {"mapFormat": {HOTA_FORMAT: {"supported": False}}}}
    on: dict[str, JsonValue] = {"settings": {"mapFormat": {HOTA_FORMAT: SECTION}}}
    manifests = {
        "a": _mod(tmp_path, "a", off),
        "b": _mod(tmp_path, "b", on),
        "c": _mod(tmp_path, "c", {}),
    }
    assert read_map_format(manifests).objects[(29, 0)][0] == "flotsam"
    assert read_map_format({k: manifests[k] for k in ("a", "c")}) == NO_FORMAT

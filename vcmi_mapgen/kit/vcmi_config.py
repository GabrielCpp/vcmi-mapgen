"""Authoritative H3M (objectClass, objectSubID) -> VCMI 'type::subtype' identifiers,
read directly from VCMI's own config (the source of truth the editor uses). No guessing.

config/objects/*.json :
    { "<type>": { "index": <class>, "types": { "<subtype>": {"index": <subID>} } } }
config/creatures/*.json, config/factions/*.json :
    { "<identifier>": { "index": <id> } }  (for monster/town subtypes)
"""

import glob
import os
import re
from pathlib import Path

from vcmi_mapgen.kit import json_value as jv
from vcmi_mapgen.kit import paths as vcmi_paths
from vcmi_mapgen.models import JsonValue

_BASES = [*vcmi_paths.vcmi_config_dirs(), os.path.join(vcmi_paths.vcmi_home(), "Mods")]


def _relaxed(t: str) -> JsonValue:
    t = re.sub(r"//[^\n]*", "", t)
    t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
    t = re.sub(r",(\s*[}\]])", r"\1", t)
    return jv.loads(t)


def _files(sub: str) -> list[str]:
    out: list[str] = []
    for b in _BASES:
        out += glob.glob(f"{b}/**/config/{sub}/*.json", recursive=True) + glob.glob(
            f"{b}/{sub}/*.json"
        )
    return sorted(set(out))


def _index_map(sub: str) -> dict[int, str]:  # identifier -> index  ==>  index -> identifier
    m: dict[int, str] = {}
    for f in _files(sub):
        try:
            d = jv.as_object(_relaxed(Path(f).read_text()))
        except Exception:
            continue
        for ident, obj in d.items():
            index = jv.opt_int(jv.as_object(obj).get("index"))
            if index is not None and index not in m:
                m[index] = ident
    return m


CLS2TYPE: dict[
    int, tuple[str, dict[int, str]]
] = {}  # objectClass -> (typeName, {subID: subtypeName})


def _load_objects() -> None:
    for f in _files("objects"):
        try:
            d = jv.as_object(_relaxed(Path(f).read_text()))
        except Exception:
            continue
        for tname, raw in d.items():
            obj = jv.as_object(raw)
            index = jv.opt_int(obj.get("index"))
            if index is None:
                continue
            subs: dict[int, str] = {}
            for sname, s in jv.as_object(obj.get("types")).items():
                sub_index = jv.opt_int(jv.as_object(s).get("index"))
                if sub_index is not None:
                    subs[sub_index] = sname
            CLS2TYPE.setdefault(index, (tname, {}))[1].update(subs)


_load_objects()
_CREATURE = _index_map("creatures")
_FACTION = _index_map("factions")
_HERO = _index_map("heroes")
_SPELL = _index_map("spells")


def _single_map(
    relpath: str,
) -> dict[int, str]:  # for single-file configs like config/artifacts.json
    m: dict[int, str] = {}
    for b in _BASES:
        for f in [*glob.glob(f"{b}/**/{relpath}", recursive=True), f"{b}/{relpath}"]:
            if not os.path.isfile(f):
                continue
            try:
                d = jv.as_object(_relaxed(Path(f).read_text()))
            except Exception:
                continue
            for ident, obj in d.items():
                index = jv.opt_int(jv.as_object(obj).get("index"))
                if index is not None and index not in m:
                    m[index] = ident
    return m


_ARTIFACT = _single_map("artifacts.json")

# object types whose subtype comes from another registry, not config/objects
_BY_CREATURE = {"monster", "randomMonster"}
_BY_FACTION = {"town", "randomTown"}
_BY_HERO = {"hero", "randomHero", "prison", "heroPlaceholder"}


def resolve(obj_class: int, obj_subid: int) -> tuple[str, str] | None:
    """-> (type, subtype) or None if unknown."""
    e = CLS2TYPE.get(obj_class)
    if not e:
        return None
    tname, subs = e
    if obj_subid in subs:  # inline subtype (decoration/mine/resource/monolith...)
        return tname, subs[obj_subid]
    if tname in _BY_CREATURE:
        return tname, _CREATURE.get(obj_subid, "imp")
    if tname in _BY_FACTION:
        return tname, _FACTION.get(obj_subid, "castle")
    if tname in _BY_HERO:
        return tname, _HERO.get(obj_subid, "christian")
    if tname == "artifact":
        return tname, _ARTIFACT.get(obj_subid, "spellBook")
    if tname == "spellScroll":
        return tname, _SPELL.get(obj_subid, "magicArrow")
    if subs:  # has subtypes but subID unlisted -> first valid
        return tname, sorted(subs.values())[0]
    return tname, "object"  # typeless object


if __name__ == "__main__":
    print(
        f"object classes: {len(CLS2TYPE)}  creatures: {len(_CREATURE)}  factions: {len(_FACTION)}"
    )
    for c, s in [
        (134, 0),
        (101, 0),
        (53, 6),
        (79, 6),
        (54, 0),
        (98, 0),
        (45, 2),
        (5, 0),
    ]:
        print(f"  class {c} sub {s} -> {resolve(c, s)}")

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
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from vcmi_mapgen.core.model import JsonValue
from vcmi_mapgen.vcmi.formats import json_value as jv
from vcmi_mapgen.vcmi.install import VcmiInstall

_BY_CREATURE = {"monster", "randomMonster"}
_BY_FACTION = {"town", "randomTown"}
_BY_HERO = {"hero", "randomHero", "prison", "heroPlaceholder"}


@dataclass(frozen=True, slots=True)
class VcmiConfig:
    classes: dict[int, tuple[str, dict[int, str]]] = field(default_factory=dict)
    creatures: dict[int, str] = field(default_factory=dict)
    factions: dict[int, str] = field(default_factory=dict)
    heroes: dict[int, str] = field(default_factory=dict)
    spells: dict[int, str] = field(default_factory=dict)
    artifacts: dict[int, str] = field(default_factory=dict)

    def resolve(self, obj_class: int, obj_subid: int) -> tuple[str, str] | None:
        """-> (type, subtype) or None if unknown."""
        e = self.classes.get(obj_class)
        if not e:
            return None
        tname, subs = e
        if obj_subid in subs:
            return tname, subs[obj_subid]
        if tname in _BY_CREATURE:
            return tname, self.creatures.get(obj_subid, "imp")
        if tname in _BY_FACTION:
            return tname, self.factions.get(obj_subid, "castle")
        if tname in _BY_HERO:
            return tname, self.heroes.get(obj_subid, "christian")
        if tname == "artifact":
            return tname, self.artifacts.get(obj_subid, "spellBook")
        if tname == "spellScroll":
            return tname, self.spells.get(obj_subid, "magicArrow")
        if subs:
            return tname, sorted(subs.values())[0]
        return tname, "object"


EMPTY_CONFIG = VcmiConfig()


def _relaxed(t: str) -> JsonValue:
    t = re.sub(r"//[^\n]*", "", t)
    t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
    t = re.sub(r",(\s*[}\]])", r"\1", t)
    return jv.loads(t)


def _files(bases: tuple[Path, ...], sub: str) -> list[str]:
    out: list[str] = []
    for b in bases:
        out += glob.glob(f"{b}/**/config/{sub}/*.json", recursive=True) + glob.glob(
            f"{b}/{sub}/*.json"
        )
    return sorted(set(out))


def _read_object(f: str) -> dict[str, JsonValue] | None:
    try:
        return jv.as_object(_relaxed(Path(f).read_text()))
    except Exception:
        return None


def _add_indices(m: dict[int, str], d: dict[str, JsonValue]) -> None:
    for ident, obj in d.items():
        index = jv.opt_int(jv.as_object(obj).get("index"))
        if index is not None and index not in m:
            m[index] = ident


def _index_map(bases: tuple[Path, ...], sub: str) -> dict[int, str]:
    m: dict[int, str] = {}
    for f in _files(bases, sub):
        d = _read_object(f)
        if d is not None:
            _add_indices(m, d)
    return m


def _single_map(bases: tuple[Path, ...], relpath: str) -> dict[int, str]:
    m: dict[int, str] = {}
    for b in bases:
        for f in [*glob.glob(f"{b}/**/{relpath}", recursive=True), f"{b}/{relpath}"]:
            if not os.path.isfile(f):
                continue
            d = _read_object(f)
            if d is not None:
                _add_indices(m, d)
    return m


def _class_map(bases: tuple[Path, ...]) -> dict[int, tuple[str, dict[int, str]]]:
    classes: dict[int, tuple[str, dict[int, str]]] = {}
    for f in _files(bases, "objects"):
        d = _read_object(f)
        if d is None:
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
            classes.setdefault(index, (tname, {}))[1].update(subs)
    return classes


@cache
def load_config(install: VcmiInstall) -> VcmiConfig:
    bases = (*install.config_dirs, install.mods_dir)
    return VcmiConfig(
        classes=_class_map(bases),
        creatures=_index_map(bases, "creatures"),
        factions=_index_map(bases, "factions"),
        heroes=_index_map(bases, "heroes"),
        spells=_index_map(bases, "spells"),
        artifacts=_single_map(bases, "artifacts.json"),
    )

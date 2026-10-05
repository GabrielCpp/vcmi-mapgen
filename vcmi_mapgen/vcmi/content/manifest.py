"""`ModManifest`: what one installed mod's ``mod.json`` declares about the mods around it."""

from dataclasses import dataclass
from pathlib import Path

from vcmi_mapgen.core.model import JsonValue
from vcmi_mapgen.vcmi.formats import json_value as jv

MOD_FILE = "mod.json"
SUBMOD_DIR = "mods"


@dataclass(frozen=True, slots=True)
class ModManifest:
    """One mod by its dotted id: the mods it needs, the mods it cannot run beside, its
    direct submods, and whether it stays off unless named. A saved map names it by its
    display name, version and parent, and its folder holds the object configs it lists."""

    mod_id: str
    depends: frozenset[str] = frozenset()
    conflicts: frozenset[str] = frozenset()
    submods: tuple[str, ...] = ()
    keep_disabled: bool = False
    folder: Path = Path()
    name: str = ""
    version: str = ""
    parent: str | None = None
    objects: tuple[str, ...] = ()


def _ids(value: JsonValue | None) -> frozenset[str]:
    return frozenset(s.lower() for s in jv.str_list(value))


def _read(folder: Path, mod_id: str, parent: str | None) -> list[ModManifest]:
    doc = jv.as_object(jv.loads_relaxed((folder / MOD_FILE).read_text(encoding="utf-8-sig")))
    subs = [
        sub
        for sub_dir in sorted(folder.iterdir())
        if sub_dir.name.lower() == SUBMOD_DIR and sub_dir.is_dir()
        for sub in sorted(sub_dir.iterdir())
        if (sub / MOD_FILE).is_file()
    ]
    direct = tuple(f"{mod_id}.{sub.name.lower()}" for sub in subs)
    children = [m for sub, sid in zip(subs, direct, strict=True) for m in _read(sub, sid, mod_id)]
    depends = _ids(doc.get("depends")) | frozenset([parent] if parent else [])
    manifest = ModManifest(
        mod_id,
        depends,
        _ids(doc.get("conflicts")),
        direct,
        jv.opt_bool(doc.get("keepDisabled")) is True,
        folder,
        jv.as_str(doc.get("name"), mod_id),
        jv.as_str(doc.get("version")),
        parent,
        tuple(jv.str_list(doc.get("objects"))),
    )
    return [manifest, *children]


def read_manifests(mods_dir: Path) -> dict[str, ModManifest]:
    """Every mod installed under ``mods_dir`` and its submods, by dotted id. A submod's id
    is its folder name after its parent's id, and it depends on its parent."""
    if not mods_dir.is_dir():
        return {}
    found = [
        m
        for folder in sorted(mods_dir.iterdir())
        if (folder / MOD_FILE).is_file()
        for m in _read(folder, folder.name.lower(), None)
    ]
    return {m.mod_id: m for m in found}

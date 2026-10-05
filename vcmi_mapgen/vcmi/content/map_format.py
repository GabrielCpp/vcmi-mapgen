"""`MapFormat`: how an enabled mod renames the objects of a non-base `.h3m` format.

A map-support mod such as HotA's ``mapSupport`` declares, under
``settings.mapFormat.<format>`` of its ``mod.json``, which VCMI identity each `.h3m`
class and subclass stands for, which VCMI animation each `.h3m` template animation
stands for, and the `.h3m` index of each creature, faction, hero and artifact it adds.
VCMI reads the same table in ``MapIdentifiersH3M::loadMapping``.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from vcmi_mapgen.core.model import JsonValue
from vcmi_mapgen.vcmi.config import VcmiConfig
from vcmi_mapgen.vcmi.content.manifest import MOD_FILE, ModManifest
from vcmi_mapgen.vcmi.formats import json_value as jv

HOTA_FORMAT = "hornOfTheAbyss"
DEF_SUFFIX = ".def"


@dataclass(frozen=True, slots=True)
class MapFormat:
    """The renames one `.h3m` format needs. Empty when no enabled mod supports it."""

    objects: Mapping[tuple[int, int], tuple[str, str]] = field(
        default_factory=dict[tuple[int, int], tuple[str, str]]
    )
    templates: Mapping[str, str] = field(default_factory=dict[str, str])
    creatures: Mapping[int, str] = field(default_factory=dict[int, str])
    factions: Mapping[int, str] = field(default_factory=dict[int, str])
    heroes: Mapping[int, str] = field(default_factory=dict[int, str])
    artifacts: Mapping[int, str] = field(default_factory=dict[int, str])

    def animation(self, h3m_animation: str) -> str:
        """The VCMI animation of an `.h3m` template animation, without its suffix."""
        stem = _stem(h3m_animation)
        return self.templates.get(stem.lower(), stem)

    def config(self, base: VcmiConfig) -> VcmiConfig:
        """``base`` with this format's identities laid over it. The format wins a clash."""
        return replace(
            base,
            objects={**base.objects, **self.objects},
            creatures={**base.creatures, **self.creatures},
            factions={**base.factions, **self.factions},
            heroes={**base.heroes, **self.heroes},
            artifacts={**base.artifacts, **self.artifacts},
        )


NO_FORMAT = MapFormat()


def _stem(animation: str) -> str:
    return animation[: -len(DEF_SUFFIX)] if animation.lower().endswith(DEF_SUFFIX) else animation


def _pair(value: JsonValue) -> tuple[int, int] | None:
    items = jv.as_list(value)
    if len(items) != 2:
        return None
    cls, sub = (jv.opt_int(v) for v in items)
    return None if cls is None or sub is None else (cls, sub)


def _objects(table: dict[str, JsonValue]) -> dict[tuple[int, int], tuple[str, str]]:
    found: dict[tuple[int, int], tuple[str, str]] = {}
    for outer in sorted(table):
        entry = table[outer]
        inner = jv.as_object(entry) if isinstance(entry, dict) else {outer: entry}
        for name in sorted(inner):
            key = _pair(inner[name])
            if key is not None:
                found[key] = (outer, name)
    return found


def _indices(table: JsonValue | None) -> dict[int, str]:
    found: dict[int, str] = {}
    for name, raw in jv.as_object(table).items():
        index = jv.opt_int(raw)
        if index is not None:
            found[index] = name
    return found


def _templates(table: JsonValue | None) -> dict[str, str]:
    return {_stem(jv.as_str(h3m)).lower(): _stem(vcmi) for vcmi, h3m in jv.as_object(table).items()}


def _section(manifest: ModManifest, fmt: str) -> dict[str, JsonValue] | None:
    path = manifest.folder / MOD_FILE
    if not path.is_file():
        return None
    doc = jv.as_object(jv.loads_relaxed(path.read_text(encoding="utf-8-sig")))
    formats = jv.as_object(jv.as_object(doc.get("settings")).get("mapFormat"))
    section = jv.opt_object(formats.get(fmt))
    if section is None or jv.opt_bool(section.get("supported")) is not True:
        return None
    return section


def parse_map_format(section: dict[str, JsonValue]) -> MapFormat:
    """The renames one ``settings.mapFormat.<format>`` table declares."""
    return MapFormat(
        objects=_objects(jv.as_object(section.get("objects"))),
        templates=_templates(section.get("templates")),
        creatures=_indices(section.get("creatures")),
        factions=_indices(section.get("factions")),
        heroes=_indices(section.get("heroes")),
        artifacts=_indices(section.get("artifacts")),
    )


def read_map_format(manifests: Mapping[str, ModManifest], fmt: str = HOTA_FORMAT) -> MapFormat:
    """The renames for ``fmt`` the first of the enabled mods in ``manifests`` that supports
    it declares, mods in id order."""
    for mod_id in sorted(manifests):
        section = _section(manifests[mod_id], fmt)
        if section is not None:
            return parse_map_format(section)
    return NO_FORMAT

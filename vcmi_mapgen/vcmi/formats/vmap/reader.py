"""VmapDocument reader: unzips a `.vmap` and parses it into a full, structured,
round-trip-safe `VmapDocument` -- header players/teams/victory/defeat, every
object's identity/mask/options, and terrain as VCMI tile strings.

This is a STRUCTURAL reader only: it does not reconstruct the engine-internal mask
charset (see `vcmi.formats.vmap.terrain.vcmi_mask`'s docstring) -- `VmapObject.mask` is exactly
what the file's `template.mask` says, which is lossy for the 'X' vs 'A' distinction.
Callers that need the internal charset (blocking/visitable classification) must
re-derive it from the ontology by object identity, not from this field.
"""

from __future__ import annotations

import re
import zipfile
from typing import TypedDict

from vcmi_mapgen.models import JsonValue
from vcmi_mapgen.vcmi.formats import json_value as jv
from vcmi_mapgen.vcmi.formats.vmap.document import PlayerSlot, VmapDocument, VmapObject

_PLAYER_MODELED = {"canPlay", "team", "mainTown", "allowedFactions", "randomFaction"}
_HEADER_MODELED = {
    "name",
    "mapLevels",
    "players",
    "teams",
    "triggeredEvents",
    "victoryIconIndex",
    "victoryMessage",
    "defeatIconIndex",
    "defeatMessage",
}


class HeaderFields(TypedDict):
    players: list[PlayerSlot]
    teams: list[list[str]] | None
    victory_icon_index: int | None
    victory_message: dict[str, JsonValue] | None
    defeat_icon_index: int | None
    defeat_message: dict[str, JsonValue] | None
    triggered_events: dict[str, JsonValue] | None
    extra: dict[str, JsonValue]


def _relaxed(text: str) -> JsonValue:
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return jv.loads(text)


def _player_slot(color: str, pl: dict[str, JsonValue]) -> PlayerSlot:
    return PlayerSlot(
        id=color,
        can_play=jv.as_str(pl.get("canPlay"), "false"),
        team=jv.opt_int(pl.get("team")),
        main_town=jv.opt_object(pl.get("mainTown")),
        allowed_factions=jv.opt_object(pl.get("allowedFactions")),
        random_faction=jv.opt_bool(pl.get("randomFaction")),
        extra={k: v for k, v in pl.items() if k not in _PLAYER_MODELED},
    )


def _object(o: dict[str, JsonValue]) -> VmapObject:
    tmpl = jv.as_object(o.get("template"))
    return VmapObject(
        instance_name=jv.as_str(o.get("instanceName")),
        type=jv.as_str(o.get("type")),
        subtype=jv.as_str(o.get("subtype")),
        level=jv.as_int(o.get("l")),
        x=jv.as_int(o["x"]),
        y=jv.as_int(o["y"]),
        animation=jv.as_str(tmpl.get("animation")),
        editor_animation=jv.as_str(tmpl.get("editorAnimation")),
        mask=jv.str_list(tmpl.get("mask")),
        visitable_from=jv.opt_str_list(tmpl.get("visitableFrom")),
        options=jv.opt_object(o.get("options")),
    )


def _teams(value: JsonValue | None) -> list[list[str]] | None:
    if not isinstance(value, list):
        return None
    return [jv.str_list(group) for group in value]


def header_fields(header: dict[str, JsonValue]) -> HeaderFields:
    """A raw `header.json` dict -> the VmapDocument kwargs it carries (players, teams,
    victory/defeat, `extra`). Reusable wherever a document is built from a bare header
    dict rather than a whole `.vmap` file -- e.g. from a real RMG-produced header, or
    the static `data/vmap_header_template.json` fallback (see
    `renderers.vmap.VmapRenderer._build_document`).
    """
    return {
        "players": [
            _player_slot(color, pl)
            for color, pl in jv.as_object(header.get("players")).items()
            if isinstance(pl, dict)
        ],
        "teams": _teams(header.get("teams")),
        "victory_icon_index": jv.opt_int(header.get("victoryIconIndex")),
        "victory_message": jv.opt_object(header.get("victoryMessage")),
        "defeat_icon_index": jv.opt_int(header.get("defeatIconIndex")),
        "defeat_message": jv.opt_object(header.get("defeatMessage")),
        "triggered_events": jv.opt_object(header.get("triggeredEvents")),
        "extra": {k: v for k, v in header.items() if k not in _HEADER_MODELED},
    }


def read_header(path: str) -> dict[str, JsonValue]:
    """Just the raw `header.json` dict of a `.vmap` file -- for a caller that wants
    a template header (e.g. a real local RMG-produced map) to build a fresh
    `VmapDocument` from via `header_fields`, without reading the whole file."""
    with zipfile.ZipFile(path) as z:
        return jv.as_object(_relaxed(z.read("header.json").decode("utf-8", "replace")))


def _grid(value: JsonValue) -> list[list[str]]:
    return [jv.str_list(row) for row in jv.as_list(value)]


def read(path: str) -> VmapDocument:
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        header = jv.as_object(_relaxed(z.read("header.json").decode("utf-8", "replace")))
        surf = _grid(_relaxed(z.read("surface_terrain.json").decode()))
        under = (
            _grid(_relaxed(z.read("underground_terrain.json").decode()))
            if "underground_terrain.json" in names
            else None
        )
        raw_objs = jv.as_list(_relaxed(z.read("objects.json").decode("utf-8", "replace")))

    name_struct = jv.as_object(header.get("name"))
    name = jv.as_str((jv.as_list(name_struct.get("exactStrings")) or [""])[0]) or ""
    levels = jv.as_object(header.get("mapLevels"))
    surface = jv.as_object(levels.get("surface"))
    width = jv.as_int(surface.get("width"), len(surf[0]) if surf else 0)
    height = jv.as_int(surface.get("height"), len(surf))
    two_level = "underground" in levels and under is not None

    terrain = [surf] + ([under] if two_level and under is not None else [])

    return VmapDocument(
        name=name,
        width=width,
        height=height,
        two_level=two_level,
        terrain=terrain,
        objects=[_object(jv.as_object(o)) for o in raw_objs],
        **header_fields(header),
    )

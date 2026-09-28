"""VmapDocument writer: serializes a `VmapDocument` back into a real `.vmap` zip.

Builds `header.json` from `doc.extra` (whatever this document didn't specifically
model -- rumors, disposedHeroes, allowed*, version numbers, ...) overlaid with the
modeled fields (name, mapLevels, players, teams, victory/defeat) -- the direct
replacement for both the old "clone a template and patch two keys" writer and
`VmapRenderer._apply_playability`'s raw zip surgery.
"""

from __future__ import annotations

import json
import os
import zipfile

from vcmi_mapgen.models import JsonValue
from vcmi_mapgen.vcmi.formats.vmap.document import PlayerSlot, VmapDocument, VmapObject


def _name_struct(s: str) -> dict[str, JsonValue]:
    return {
        "exactStrings": [s],
        "localStrings": None,
        "message": [0],
        "numbers": None,
        "stringsTextID": None,
    }


def _player_dict(slot: PlayerSlot) -> dict[str, JsonValue]:
    d = dict(slot.extra)
    d["canPlay"] = slot.can_play
    d["mainTown"] = slot.main_town
    optional: tuple[tuple[str, JsonValue], ...] = (
        ("team", slot.team),
        ("allowedFactions", slot.allowed_factions),
        ("randomFaction", slot.random_faction),
    )
    for key, value in optional:
        if value is not None:
            d[key] = value
        elif key in d:
            del d[key]
    return d


def _object_dict(o: VmapObject) -> dict[str, JsonValue]:
    tmpl: dict[str, JsonValue] = {
        "animation": o.animation,
        "editorAnimation": o.editor_animation,
        "mask": list[JsonValue](o.mask),
    }
    if o.visitable_from:
        tmpl["visitableFrom"] = list[JsonValue](o.visitable_from)
    d: dict[str, JsonValue] = {
        "instanceName": o.instance_name,
        "l": o.level,
        "type": o.type,
        "subtype": o.subtype,
        "template": tmpl,
        "x": o.x,
        "y": o.y,
    }
    if o.options:
        d["options"] = dict(o.options)
    return d


def _build_header(doc: VmapDocument) -> dict[str, JsonValue]:
    h = dict(doc.extra)
    h["name"] = _name_struct(doc.name)
    ml: dict[str, JsonValue] = {
        "surface": {"height": doc.height, "index": 0, "layer": "core:surface", "width": doc.width}
    }
    if doc.two_level:
        under = doc.terrain[1]
        ml["underground"] = {
            "height": len(under),
            "index": 1,
            "layer": "core:underground",
            "width": len(under[0]) if under else doc.width,
        }
    h["mapLevels"] = ml
    h["players"] = {slot.id: _player_dict(slot) for slot in doc.players}
    if doc.teams is not None:
        h["teams"] = [list[JsonValue](group) for group in doc.teams]
    elif "teams" in h:
        del h["teams"]
    optional: tuple[tuple[str, JsonValue], ...] = (
        ("victoryIconIndex", doc.victory_icon_index),
        ("victoryMessage", doc.victory_message),
        ("defeatIconIndex", doc.defeat_icon_index),
        ("defeatMessage", doc.defeat_message),
        ("triggeredEvents", doc.triggered_events),
    )
    for key, value in optional:
        if value is not None:
            h[key] = value
    return h


def write(doc: VmapDocument, path: str) -> str:
    header = _build_header(doc)
    files = {
        "header.json": json.dumps(header, indent=1),
        "surface_terrain.json": json.dumps(doc.terrain[0]),
        "objects.json": json.dumps([_object_dict(o) for o in doc.objects], indent=1),
    }
    if doc.two_level:
        files["underground_terrain.json"] = json.dumps(doc.terrain[1])
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return path

"""A `.vmap` file to a `MapState`, the inverse of export."""

from __future__ import annotations

from vcmi_mapgen.core.model import MapState, PlacedObject
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.road import Road
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.reading.ground import TownKey
from vcmi_mapgen.vcmi.catalog import objects as ON
from vcmi_mapgen.vcmi.footprint import footprint_of
from vcmi_mapgen.vcmi.formats import vmap as VM
from vcmi_mapgen.vcmi.tiles import decode_tile_string


def load_map(path: str) -> MapState:
    """Load a `.vmap` into a MapState with `terrain`, `roads`, `objs` and `size`. Each tile
    keeps its terrain and its road type and drops its art. Fields a `.vmap` does not store
    (zones, gate_blk, player_towns) keep their defaults.

    Each object's footprint is re-derived from the ontology by animation
    (`vcmi.catalog.objects.mask_of`), NOT read from the file's `template.mask`, which cannot
    tell a blocked-entrance 'X' cell from a walk-on 'A' one (see
    `vcmi.formats.vmap.terrain.vcmi_mask`). Objects the ontology has no data for (heroes,
    whose per-portrait animations are not in objects.txt) fall back to the file's own mask. A
    hero's 1-tile mask has no 'B' cell, so the file's charset is unambiguous for it.
    """
    doc = VM.read(path)
    state = MapState(size=max(doc.width, doc.height))
    for level, grid in enumerate(doc.terrain):
        cells = [[decode_tile_string(t) for t in row] for row in grid]
        state.terrain[level] = [[Terrain(c.t) for c in row] for row in cells]
        state.roads[level] = {
            (x, y): Road(c.ot) for y, row in enumerate(cells) for x, c in enumerate(row) if c.ot
        }
    state.objs = [
        PlacedObject(
            x=o.x,
            y=o.y,
            level=o.level,
            purpose=ON.purpose_of_type(o.type) or Purpose.UNKNOWN,
            kind=o.animation,
            footprint=footprint_of(
                ON.mask_of(o.animation) if ON.has_animation(o.animation) else o.mask
            ),
        )
        for o in doc.objects
    ]
    return state


def map_owners(path: str) -> dict[TownKey, int]:
    """Town position ``(x, y, level)`` -> owner for every owned town of a `.vmap`. A player's
    index is its colour's rank among the header's colours sorted by name, the order export
    wires the player towns in, so a generated map reads back the owners it was built with."""
    doc = VM.read(path)
    ids = sorted(p.id for p in doc.players)
    return {
        (o.x, o.y, o.level): ids.index(owner)
        for o in doc.objects
        if isinstance(owner := (o.options or {}).get("owner"), str) and owner in ids
    }

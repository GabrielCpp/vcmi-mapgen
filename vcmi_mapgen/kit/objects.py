"""Object identity & faithful-map catalog — the shared, generic lookup layer.

Two sources of truth, both already byte-exact:

  * ``maps_vmap/<name>.vmap``  — every corpus object carries its EXACT
    ``type, subtype, animation`` (built from the real .h3m template) plus a footprint
    ``mask`` re-derived from the ontology by animation (see :func:`load_faithful` --
    a real .vmap's own ``template.mask`` can't distinguish a blocked-entrance 'X' cell
    from a walk-on 'A' one, so it is never trusted directly). Use :func:`exact_identity`
    to reproduce a corpus object identically.
  * ``data/objlib.json`` — ``purpose -> terrain_id -> [ {type, subtype, animation,
    mask, weight}, ... ]`` — the catalog of interchangeable concrete objects per
    purpose+terrain, harvested from the corpus.

The terrain cells in a faithful map ({t,view,rt,rd,ot,od,m}) are already what
``rebuild.engine.fm_to_document`` / ``kit.vmap.terrain.tile_string`` expect, so a generated
map can pass faithful terrain straight through.
"""
from __future__ import annotations

import json
import os

from vcmi_mapgen import ontology as ON
from vcmi_mapgen.kit import vmap as VM
from vcmi_mapgen.kit.paths import project_root
from vcmi_mapgen.kit.vmap.terrain import decode_tile_string

ROOT = project_root()
_OBJLIB = json.load(open(str(ROOT / "data" / "objlib.json")))

# Identity fields a faithful object carries that the .vmap writer needs.
_IDENT_KEYS = ("type", "subtype", "animation", "mask")


# ---------------------------------------------------------------------------
# Corpus loading
# ---------------------------------------------------------------------------

def faithful_path(name: str) -> str:
    return str(ROOT / "maps_vmap" / f"{name}.vmap")


def load_faithful(name: str) -> dict:
    """Load a byte-exact faithful map: terrain (writer-ready) + objects (exact mask).

    Adapts the real .vmap this corpus map now lives as (via `kit.vmap.reader`) into the
    plain-dict shape the rest of the engine expects. Each object's `mask` is re-derived
    from the ontology by animation (`ontology.mask_of`), NOT read from the file's
    `template.mask` -- see the module docstring and `kit.vmap.terrain.vcmi_mask` for why
    that field is lossy for the 'X' vs 'A' distinction `is_blocking`/`mask_cells` depend on.
    Objects the ontology has no data for at all (heroes -- their per-portrait animations
    aren't in objects.txt's catalog) fall back to the file's own mask instead of the
    ontology accessor's conservative all-blocking default; a hero's 1-tile mask has no
    'B' cell to begin with, so the file's charset is unambiguous for it.
    """
    doc = VM.read(faithful_path(name))
    terrain = [[[decode_tile_string(s) for s in row] for row in lvl] for lvl in doc.terrain]
    objects = [
        {
            "x": o.x, "y": o.y, "l": o.l,
            "type": o.type, "subtype": o.subtype,
            "animation": o.animation,
            "mask": ON.mask_of(o.animation) if ON.has_animation(o.animation) else o.mask,
        }
        for o in doc.objects
    ]
    return {
        "name": doc.name, "width": doc.width, "height": doc.height,
        "twoLevel": doc.two_level, "terrain": terrain, "objects": objects,
    }


def all_map_names() -> list[str]:
    d = ROOT / "maps_vmap"
    return [os.path.splitext(f)[0] for f in sorted(os.listdir(d)) if f.endswith(".vmap")]


# ---------------------------------------------------------------------------
# Object classification & exact identity
# ---------------------------------------------------------------------------

_TYPE2PURPOSE = {it["type"]: p for p, terr in _OBJLIB.items()
                 for items in terr.values() for it in items}


def type_to_purpose(type_name: str) -> str | None:
    """Purpose for an object TYPE alone -- built from the same objlib.json catalog
    harvested from the corpus. The only lookup a real .vmap object's type/subtype
    supports (it carries no raw h3m cls/sub)."""
    return _TYPE2PURPOSE.get(type_name)


def purpose_of(obj: dict) -> str:
    """Purpose of a faithful (corpus) or generated object, keyed by its `type` alone."""
    return type_to_purpose(obj.get("type")) or "UNKNOWN"


def exact_identity(obj: dict) -> dict:
    """The exact {type, subtype, animation, mask} of a corpus object."""
    return {k: obj[k] for k in _IDENT_KEYS}


def is_blocking(mask: list[str]) -> bool:
    """True if the object's footprint blocks movement (mask has a 'B' or 'X' cell — 'X' is a
    blocked-and-visitable building action tile)."""
    return any(ch in "BX" for row in mask for ch in row)


def mask_cells(mask: list[str], x: int, y: int):
    """Tiles a mask covers when anchored at (x, y).

    Convention: anchor (x, y) is the BOTTOM-RIGHT tile of the footprint. Mask rows are stored
    LEFT-TO-RIGHT, sprite-aligned (matching `kit.vmap.mask.build_mask_from_h3m` and `ontology._decode_mask`),
    so column 0 is the LEFTMOST tile and the anchor is the LAST column of each row ->
    `tx = x - (ww - 1 - c)` where `ww = len(row)`. (Verified pixel-for-pixel against real sprite
    art: a sawmill's ramp/visit tile and a pine clump's trunks land on the correct side only with
    this formula -- the plain `x - c` mirrors every asymmetric footprint horizontally.)
    'B' = blocking, 'X' = blocking + visitable, 'A' = passable + visitable, 'V' = passable
    overlay, ' ' = empty. Yields (tx, ty, blocking_bool) per non-empty cell.
    """
    hh = len(mask)
    for r, row in enumerate(mask):
        ww = len(row)
        for c, ch in enumerate(row):
            if ch == " ":
                continue
            yield x - (ww - 1 - c), y - (hh - 1 - r), (ch in ("B", "X"))


def mask_interactive_cells(mask: list[str], x: int, y: int):
    """The subset of `mask_cells` a hero must actually step on to trigger this object --
    visitable ('A') or blocking+visitable ('X') -- as opposed to pure passable overlay
    ('V') or solid-but-inert ('B'). A guard's other footprint cells are cosmetic canopy;
    only this cell needs to be free & reachable for the object to functionally gate a tile."""
    hh = len(mask)
    out = []
    for r, row in enumerate(mask):
        ww = len(row)
        for c, ch in enumerate(row):
            if ch in ("A", "X"):
                out.append((x - (ww - 1 - c), y - (hh - 1 - r)))
    return out


if __name__ == "__main__":
    names = all_map_names()
    print(f"faithful maps: {len(names)}  objlib purposes: {sorted(_OBJLIB)}")
    m = load_faithful("All for One")
    from collections import Counter
    pc = Counter(purpose_of(o) for o in m["objects"])
    print("All for One purposes:", dict(pc.most_common()))
    o = m["objects"][0]
    print("exact identity sample:", exact_identity(o), "blocking=", is_blocking(o["mask"]))

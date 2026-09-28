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
``renderers.vmap.VmapRenderer`` / ``vcmi.formats.vmap.terrain.tile_string`` expect, so a generated
map can pass faithful terrain straight through.
"""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Container, Iterable, Iterator, Sequence
from dataclasses import dataclass

from vcmi_mapgen import ontology as ON
from vcmi_mapgen.kit.paths import project_root
from vcmi_mapgen.models import Cell, Identity, PlacedObject, Tile
from vcmi_mapgen.vcmi.formats import json_value as jv
from vcmi_mapgen.vcmi.formats import vmap as VM
from vcmi_mapgen.vcmi.formats.vmap.terrain import decode_tile_string

ROOT = project_root()
_OBJLIB = jv.as_object(jv.loads((ROOT / "data" / "objlib.json").read_text()))


@dataclass(frozen=True, slots=True)
class FaithfulMap:
    name: str
    width: int
    height: int
    two_level: bool
    terrain: list[list[list[Cell]]]
    objects: list[PlacedObject]
    main_town: Tile | None = None


# ---------------------------------------------------------------------------
# Corpus loading
# ---------------------------------------------------------------------------


def faithful_path(name: str) -> str:
    return str(ROOT / "maps_vmap" / f"{name}.vmap")


def load_faithful(name: str) -> FaithfulMap:
    """Load a byte-exact faithful map: terrain (writer-ready) + objects (exact mask).

    Adapts the real .vmap this corpus map now lives as (via `vcmi.formats.vmap.reader`) into the
    `FaithfulMap` shape the rest of the engine expects. Each object's `mask` is re-derived
    from the ontology by animation (`ontology.mask_of`), NOT read from the file's
    `template.mask` -- see the module docstring and `vcmi.formats.vmap.terrain.vcmi_mask` for why
    that field is lossy for the 'X' vs 'A' distinction `is_blocking`/`mask_cells` depend on.
    Objects the ontology has no data for at all (heroes -- their per-portrait animations
    aren't in objects.txt's catalog) fall back to the file's own mask instead of the
    ontology accessor's conservative all-blocking default; a hero's 1-tile mask has no
    'B' cell to begin with, so the file's charset is unambiguous for it.
    """
    doc = VM.read(faithful_path(name))
    terrain = [[[decode_tile_string(s) for s in row] for row in lvl] for lvl in doc.terrain]
    objects = [
        PlacedObject(
            x=o.x,
            y=o.y,
            level=o.level,
            purpose=type_to_purpose(o.type) or "UNKNOWN",
            type=o.type,
            subtype=o.subtype,
            animation=o.animation,
            mask=ON.mask_of(o.animation) if ON.has_animation(o.animation) else tuple(o.mask),
        )
        for o in doc.objects
    ]
    return FaithfulMap(
        name=doc.name,
        width=doc.width,
        height=doc.height,
        two_level=doc.two_level,
        terrain=terrain,
        objects=objects,
    )


def all_map_names() -> list[str]:
    d = ROOT / "maps_vmap"
    return [os.path.splitext(f)[0] for f in sorted(os.listdir(d)) if f.endswith(".vmap")]


def corpus_maps() -> list[FaithfulMap]:
    maps: list[FaithfulMap] = []
    for name in all_map_names():
        try:
            maps.append(load_faithful(name))
        except Exception:
            continue
    return maps


# ---------------------------------------------------------------------------
# Object classification & exact identity
# ---------------------------------------------------------------------------

_TYPE2PURPOSE: dict[str, str] = {
    jv.as_str(jv.as_object(it).get("type")): p
    for p, terr in _OBJLIB.items()
    for items in jv.as_object(terr).values()
    for it in jv.as_list(items)
}


def type_to_purpose(type_name: str | None) -> str | None:
    """Purpose for an object TYPE alone -- built from the same objlib.json catalog
    harvested from the corpus. The only lookup a real .vmap object's type/subtype
    supports (it carries no raw h3m cls/sub)."""
    return _TYPE2PURPOSE.get(type_name) if type_name is not None else None


def purpose_of(obj: PlacedObject) -> str:
    """Purpose of a faithful (corpus) or generated object, keyed by its `type` alone."""
    return type_to_purpose(obj.type) or "UNKNOWN"


def exact_identity(obj: PlacedObject) -> Identity:
    """The exact {type, subtype, animation, mask} of a corpus object."""
    return Identity(type=obj.type, subtype=obj.subtype, animation=obj.animation, mask=obj.mask)


def is_blocking(mask: Sequence[str]) -> bool:
    """True if the object's footprint blocks movement (mask has a 'B' or 'X' cell — 'X' is a
    blocked-and-visitable building action tile)."""
    return any(ch in "BX" for row in mask for ch in row)


def mask_cells(mask: Sequence[str], x: int, y: int) -> Iterator[tuple[int, int, bool]]:
    """Tiles a mask covers when anchored at (x, y).

    Convention: anchor (x, y) is the BOTTOM-RIGHT tile of the footprint. Mask rows are stored
    LEFT-TO-RIGHT, sprite-aligned (matching `vcmi.formats.vmap.mask.build_mask_from_h3m` and
    `ontology._decode_mask`),
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


def mask_interactive_cells(mask: Sequence[str], x: int, y: int) -> list[Tile]:
    """The subset of `mask_cells` a hero must actually step on to trigger this object --
    visitable ('A') or blocking+visitable ('X') -- as opposed to pure passable overlay
    ('V') or solid-but-inert ('B'). A guard's other footprint cells are cosmetic canopy;
    only this cell needs to be free & reachable for the object to functionally gate a tile."""
    hh = len(mask)
    out: list[Tile] = []
    for r, row in enumerate(mask):
        ww = len(row)
        for c, ch in enumerate(row):
            if ch in ("A", "X"):
                out.append((x - (ww - 1 - c), y - (hh - 1 - r)))
    return out


def decor_blocking_cells(objs: Iterable[PlacedObject]) -> set[Tile]:
    """Blocking cells of every purpose-less (vegetation/decor) object in `objs`."""
    return {
        (cx, cy)
        for o in objs
        if not o.purpose
        for cx, cy, blk in mask_cells(o.mask, o.x, o.y)
        if blk
    }


def overlay_clear(mask: Sequence[str], x: int, y: int, blocked: Container[Tile]) -> bool:
    """True if none of the mask's non-interactive cells (sprite overlay) sit on `blocked`."""
    inter = set(mask_interactive_cells(mask, x, y))
    return not any(
        (tx, ty) in blocked for tx, ty, _b in mask_cells(mask, x, y) if (tx, ty) not in inter
    )


def front_tiles(mask: Sequence[str], x: int, y: int) -> set[Tile]:
    """The row of tiles directly in front of (one step past) this object's own
    footprint, on the side its interactive cell sits on. Every multi-row mask in this
    ontology places its interactive ('A'/'X') cell in the mask's LAST row (verified
    across the whole catalog: the sprite's ground-contact row) -- the one direction an
    approach is always geometrically unobstructed by the object's own body is one
    tile further in that same direction, spanning the interactive column and its two
    neighbours (s8 diagnosis, 2026-09: a later structure placed squarely in this row
    fully sealed off an existing structure's own approach, since nothing checked a new
    placement against it).

    Excludes any tile that is itself part of the object's own footprint. Empty for a
    single-row mask or one with no interactive cell (a pure decoration/vegetation
    object, or a guard's cosmetic sprite bleed) -- neither has a meaningful 'front'
    distinct from its own body, so both are naturally exempt from needing one kept
    open."""
    if len(mask) < 2:
        return set()
    footprint = {(tx, ty) for tx, ty, _b in mask_cells(mask, x, y)}
    front: set[Tile] = set()
    for ix, iy in mask_interactive_cells(mask, x, y):
        for dx in (-1, 0, 1):
            t = (ix + dx, iy + 1)
            if t not in footprint:
                front.add(t)
    return front


if __name__ == "__main__":
    names = all_map_names()
    print(f"faithful maps: {len(names)}  objlib purposes: {sorted(_OBJLIB)}")
    m = load_faithful("All for One")
    pc = Counter(purpose_of(o) for o in m.objects)
    print("All for One purposes:", dict(pc.most_common()))
    o = m.objects[0]
    print("exact identity sample:", exact_identity(o), "blocking=", is_blocking(o.mask))

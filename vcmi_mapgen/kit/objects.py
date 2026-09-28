"""Object identity & faithful-map catalog — the shared, generic lookup layer.

Two sources of truth, both already byte-exact:

  * ``maps_vmap/<name>.vmap``  — every corpus object carries its EXACT
    ``type, subtype, animation`` (built from the real .h3m template) plus a footprint
    ``mask`` re-derived from the ontology by animation (see :func:`load_faithful` --
    a real .vmap's own ``template.mask`` can't distinguish a blocked-entrance 'X' cell
    from a walk-on 'A' one, so it is never trusted directly). Use :func:`exact_identity`
    to reproduce a corpus object identically.
  * the catalog — :func:`purpose_of` answers an object's purpose from its VCMI type
    through ``vcmi.catalog.objects.purpose_of_type``.

The terrain cells in a faithful map ({t,view,rt,rd,ot,od,m}) are already what
``renderers.vmap.VmapRenderer`` / ``vcmi.formats.vmap.terrain.tile_string`` expect, so a generated
map can pass faithful terrain straight through.
"""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Container, Iterable, Iterator
from dataclasses import dataclass

from vcmi_mapgen.core.model import Cell, Footprint, Identity, PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.kit.paths import project_root
from vcmi_mapgen.vcmi.catalog import objects as ON
from vcmi_mapgen.vcmi.footprint import footprint_of
from vcmi_mapgen.vcmi.formats import vmap as VM
from vcmi_mapgen.vcmi.formats.vmap.terrain import decode_tile_string

ROOT = project_root()


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
    from the ontology by animation (`vcmi.catalog.objects.mask_of`), NOT read from the file's
    `template.mask` -- see the module docstring and `vcmi.formats.vmap.terrain.vcmi_mask` for why
    that field is lossy for the 'X' vs 'A' distinction `footprint_of`/`is_blocking` depend on.
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
            purpose=ON.purpose_of_type(o.type) or Purpose.UNKNOWN,
            type=o.type,
            subtype=o.subtype,
            animation=o.animation,
            footprint=footprint_of(
                ON.mask_of(o.animation) if ON.has_animation(o.animation) else o.mask
            ),
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


def purpose_of(obj: PlacedObject) -> Purpose:
    """Purpose of a faithful (corpus) or generated object, keyed by its `type` alone."""
    return ON.purpose_of_type(obj.type) or Purpose.UNKNOWN


def exact_identity(obj: PlacedObject) -> Identity:
    """The exact {type, subtype, animation, mask} of a corpus object."""
    return Identity(
        type=obj.type, subtype=obj.subtype, animation=obj.animation, footprint=obj.footprint
    )


def is_blocking(fp: Footprint) -> bool:
    """True if the footprint has a cell that blocks movement."""
    return any(role.blocks for _dx, _dy, role in fp.cells)


def anchored_cells(fp: Footprint, x: int, y: int) -> Iterator[tuple[int, int, bool]]:
    """(tx, ty, blocking) for every cell of `fp` anchored at (x, y)."""
    for (tx, ty), role in fp.at(x, y):
        yield tx, ty, role.blocks


def interactive_cells(fp: Footprint, x: int, y: int) -> list[Tile]:
    """The cells a hero must step on to trigger this object: its entrance and visit cells,
    as opposed to overlay or solid-but-inert body cells. A guard's other footprint cells are
    cosmetic canopy. Only this cell needs to be free and reachable for the object to gate a
    tile."""
    return [t for t, role in fp.at(x, y) if role.interactive]


def decor_blocking_cells(objs: Iterable[PlacedObject]) -> set[Tile]:
    """Blocking cells of every purpose-less (vegetation/decor) object in `objs`."""
    return {
        (cx, cy)
        for o in objs
        if not o.purpose
        for cx, cy, blk in anchored_cells(o.footprint, o.x, o.y)
        if blk
    }


def overlay_clear(fp: Footprint, x: int, y: int, blocked: Container[Tile]) -> bool:
    """True if none of the footprint's non-interactive cells (sprite overlay) sit on
    `blocked`."""
    inter = set(interactive_cells(fp, x, y))
    return not any(
        (tx, ty) in blocked for tx, ty, _b in anchored_cells(fp, x, y) if (tx, ty) not in inter
    )


def front_tiles(fp: Footprint, x: int, y: int) -> set[Tile]:
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
    if fp.height < 2:
        return set()
    footprint = {(tx, ty) for tx, ty, _b in anchored_cells(fp, x, y)}
    front: set[Tile] = set()
    for ix, iy in interactive_cells(fp, x, y):
        for dx in (-1, 0, 1):
            t = (ix + dx, iy + 1)
            if t not in footprint:
                front.add(t)
    return front


if __name__ == "__main__":
    names = all_map_names()
    print(f"faithful maps: {len(names)}")
    m = load_faithful("All for One")
    pc = Counter(purpose_of(o) for o in m.objects)
    print("All for One purposes:", dict(pc.most_common()))
    o = m.objects[0]
    print("exact identity sample:", exact_identity(o), "blocking=", is_blocking(o.footprint))

"""Footprint cell expansion: the tiles an object's `Footprint` covers once anchored."""

from __future__ import annotations

from collections.abc import Container, Iterable, Iterator
from functools import cache

from vcmi_mapgen.core.model import Footprint, PlacedObject, Role, Tile


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


def blocking_cells(objs: Iterable[PlacedObject]) -> set[Tile]:
    """Blocking cells of every object in `objs`."""
    return {(cx, cy) for o in objs for cx, cy, blk in anchored_cells(o.footprint, o.x, o.y) if blk}


def decor_blocking_cells(objs: Iterable[PlacedObject]) -> set[Tile]:
    """Blocking cells of every purpose-less (vegetation/decor) object in `objs`."""
    return blocking_cells(o for o in objs if not o.purpose)


def overlay_clear(fp: Footprint, x: int, y: int, blocked: Container[Tile]) -> bool:
    """True if none of the footprint's non-interactive cells (sprite overlay) sit on
    `blocked`."""
    inter = set(interactive_cells(fp, x, y))
    return not any(
        (tx, ty) in blocked for tx, ty, _b in anchored_cells(fp, x, y) if (tx, ty) not in inter
    )


def overlay_cells(fp: Footprint, anchor: Tile) -> frozenset[Tile]:
    """The cells of ``fp`` anchored at ``anchor`` that neither block nor interact: sprite
    overlay a hero walks under."""
    return frozenset(t for t, role in fp.at(*anchor) if not role.blocks and not role.interactive)


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


def footprint_cells(fp: Footprint, ax: int, ay: int) -> tuple[list[Tile], list[Tile], Tile | None]:
    """(all_cells, blocking_cells, approach) of a footprint anchored at (ax, ay); approach is
    the tile a hero stands on to visit: below an entrance, or a visit cell itself."""
    allc, blk, approach = cell_offsets(fp)
    return (
        [(ax + dx, ay + dy) for dx, dy in allc],
        [(ax + dx, ay + dy) for dx, dy in blk],
        None if approach is None else (ax + approach[0], ay + approach[1]),
    )


@cache
def cell_offsets(fp: Footprint) -> tuple[tuple[Tile, ...], tuple[Tile, ...], Tile | None]:
    """``footprint_cells`` of ``fp`` anchored at the origin."""
    allc: list[Tile] = []
    blk: list[Tile] = []
    approach: Tile | None = None
    for (tx, ty), role in fp.at(0, 0):
        allc.append((tx, ty))
        if role.blocks:
            blk.append((tx, ty))
        if role is Role.ENTRANCE:
            approach = (tx, ty + 1)
        elif role is Role.VISIT and approach is None:
            approach = (tx, ty)
    return tuple(allc), tuple(blk), approach

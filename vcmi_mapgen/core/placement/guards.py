"""Guard spacing and the gameplay-footprint fit every placement step shares: the GAP rule, a
guard's zone of control."""

from collections.abc import Container, Iterable, Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.model import Identity, PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.placement.footprint import footprint_cells

NO_TILES: frozenset[Tile] = frozenset()


GAP = 2  # free tiles kept between any two gameplay footprints — gameplay
# neighbours VEGETATION (which fills the gap), not other gameplay


type Fit = tuple[list[Tile], list[Tile], Tile]


@dataclass(frozen=True, slots=True)
class Clearance:
    occupied: Container[Tile]
    near: Container[Tile]
    reserved: Container[Tile]
    avoid: Container[Tile] = NO_TILES


def fits(ident: Identity, anchor: Tile, ts: Container[Tile], clear: Clearance) -> Fit | None:
    """Legality: whole footprint in-zone, at least GAP free tiles from every other gameplay
    footprint (`near` = existing cells inflated by GAP), no squatting on an earlier object's
    approach tile (`reserved`), own approach tile in-zone and standable. No cell and no
    approach may touch `avoid`, the ground a later object has claimed."""
    allc, blk, approach = footprint_cells(ident.footprint, anchor[0], anchor[1])
    if approach is None:
        return None
    for cell in allc:
        if cell not in ts or cell in clear.near or cell in clear.reserved or cell in clear.avoid:
            return None
    if approach not in ts or approach in clear.occupied or approach in blk:
        return None
    if approach in clear.avoid:
        return None
    return allc, blk, approach


def inflate_gap(near: set[Tile], cells: Iterable[Tile]) -> None:
    for cx, cy in cells:
        for gx in range(-GAP, GAP + 1):
            for gy in range(-GAP, GAP + 1):
                near.add((cx + gx, cy + gy))


GUARD_SPACING = 2


def zoc_of(t: Tile) -> set[Tile]:
    """The zone of control of a guard standing on ``t``: the tile and its 8 neighbours."""
    return {(t[0] + dx, t[1] + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)}


def guard_zoc(objs: Sequence[PlacedObject]) -> set[Tile]:
    """Every tile inside some guard's zone of control: the interactive cell plus its 8
    neighbours. A hero stepping on one of them fights the guard."""
    zoc: set[Tile] = set()
    for o in objs:
        if o.purpose != Purpose.GUARD or not o.footprint.cells:
            continue
        for t in FP.interactive_cells(o.footprint, o.x, o.y):
            zoc |= zoc_of(t)
    return zoc


def guard_spaced(t: Tile, guards: Iterable[Tile]) -> bool:
    """True when no guard in ``guards`` stands within Chebyshev ``GUARD_SPACING`` of ``t``.
    Every step that places a guard refuses a tile this rejects, so no two guards crowd one
    crossing."""
    return all(max(abs(t[0] - g[0]), abs(t[1] - g[1])) > GUARD_SPACING for g in guards)

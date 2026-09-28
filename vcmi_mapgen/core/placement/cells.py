"""Footprint legality of a pickup or guard against the open field."""

from collections.abc import Container
from dataclasses import dataclass

from vcmi_mapgen.core.model import Identity, Tile
from vcmi_mapgen.core.placement import footprint as FP


@dataclass(frozen=True, slots=True)
class CellRules:
    bounds: tuple[int, int] | None = None
    interactive_only: bool = False


DEFAULT_CELL_RULES = CellRules()


def legal_cells(
    ident: Identity,
    anchor: Tile,
    open_set: Container[Tile],
    used: Container[Tile],
    rules: CellRules = DEFAULT_CELL_RULES,
) -> list[Tile] | None:
    """A pickup/guard placement is legal if its INTERACTIVE cell(s) sit on an unused,
    placement-eligible tile.  V-overlay cells (sprite bleed) may overlap terrain/walls.

    interactive_only=True: only the interactive (A/X) cell is checked against `used` and
    bounds, and only that cell is returned for claiming.  Use this for dense fill passes
    where adjacent pickups' V-cells would otherwise falsely block each other — V cells are
    cosmetic in H3/VCMI and two objects sharing V-cell space is legal."""
    x, y = anchor
    cells = [(tx, ty) for tx, ty, _b in FP.anchored_cells(ident.footprint, x, y)]
    interactive = FP.interactive_cells(ident.footprint, x, y) or cells
    check = interactive if rules.interactive_only else cells
    if rules.bounds is not None:
        bw, bh = rules.bounds
        if any(not (0 <= tx < bw and 0 <= ty < bh) for tx, ty in check):
            return None
    if any(c in used for c in check):
        return None
    if all(c in open_set and c not in used for c in interactive):
        return check
    return None

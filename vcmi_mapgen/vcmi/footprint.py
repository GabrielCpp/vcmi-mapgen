"""The engine-internal mask charset, decoded to a core `Footprint` and encoded back.

A mask is a tuple of rows, anchored at its bottom-right cell. 'B' is blocking, 'X' is a
blocking entrance visited from the tile below, 'A' is walk-on visitable, 'V' is passable
overlay and ' ' is empty. VCMI's own file charset differs, see
`vcmi.formats.vmap.terrain.vcmi_mask`.
"""

from collections.abc import Sequence
from functools import cache

from vcmi_mapgen.core.model import Footprint, Role

type Mask = tuple[str, ...]

_ROLE = {"B": Role.BLOCKING, "X": Role.ENTRANCE, "A": Role.VISIT, "V": Role.OVERLAY}
_CHAR = {role: ch for ch, role in _ROLE.items()}


def footprint_of(mask: Sequence[str]) -> Footprint:
    return _decode(tuple(mask))


@cache
def _decode(mask: Mask) -> Footprint:
    hh = len(mask)
    cells = tuple(
        (c - (len(row) - 1), r - (hh - 1), _ROLE[ch])
        for r, row in enumerate(mask)
        for c, ch in enumerate(row)
        if ch != " "
    )
    return Footprint(max((len(row) for row in mask), default=0), hh, cells)


def sealed(mask: Sequence[str]) -> Mask:
    """The mask with every walk-on 'A' cell closed. A cell becomes an 'X' entrance visited
    from the tile below, or a 'B' when the object's own body stands on that tile."""
    return _seal(tuple(mask))


@cache
def _seal(mask: Mask) -> Mask:
    def body_below(r: int, c: int) -> bool:
        if r + 1 >= len(mask):
            return False
        row, nxt = mask[r], mask[r + 1]
        k = c - (len(row) - 1) + (len(nxt) - 1)
        return 0 <= k < len(nxt) and nxt[k] in "BXA"

    return tuple(
        "".join(("B" if body_below(r, c) else "X") if ch == "A" else ch for c, ch in enumerate(row))
        for r, row in enumerate(mask)
    )


def mask_rows(footprint: Footprint) -> Mask:
    return tuple(
        "".join(" " if role is None else _CHAR[role] for role in row) for row in footprint.grid()
    )

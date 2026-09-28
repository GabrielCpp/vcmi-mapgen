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


def mask_rows(footprint: Footprint) -> Mask:
    return tuple(
        "".join(" " if role is None else _CHAR[role] for role in row) for row in footprint.grid()
    )

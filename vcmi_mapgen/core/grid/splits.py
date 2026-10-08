"""Whether closing a few tiles parts the open land around them into two or more large
pieces, the way a guard's zone of control parts one territory into two."""

import collections
from collections.abc import Callable, Iterable

from vcmi_mapgen.core.grid.reach import STEPS8, reach
from vcmi_mapgen.core.model import Tile

MARGIN = 3
MIN_AREA = 15


def _piece(start: Tile, open_at: Callable[[Tile], bool]) -> set[Tile]:
    seen = {start}
    queue = collections.deque([start])
    while queue:
        x, y = queue.popleft()
        for dx, dy in STEPS8:
            n = (x + dx, y + dy)
            if n not in seen and open_at(n):
                seen.add(n)
                queue.append(n)
    return seen


def splits(
    cut: Iterable[Tile], open_at: Callable[[Tile], bool], min_area: int, margin: int = MARGIN
) -> bool:
    """Whether closing ``cut`` leaves two or more 8-connected open pieces of at least
    ``min_area`` tiles beside it. Open tiles beside the cut that still join within
    ``margin`` steps of it settle the answer without a walk over the whole map."""
    cut = set(cut)

    def rest(t: Tile) -> bool:
        return t not in cut and open_at(t)

    side = sorted(t for t in {(x + dx, y + dy) for x, y in cut for dx, dy in STEPS8} if rest(t))
    if len(side) < 2:
        return False
    box = {
        (x + dx, y + dy)
        for x, y in cut
        for dx in range(-margin, margin + 1)
        for dy in range(-margin, margin + 1)
    }
    near = {t for t in box if rest(t)}
    if set(side) <= reach(near, [side[0]], STEPS8):
        return False
    seen: set[Tile] = set()
    large = 0
    for s in side:
        if s in seen:
            continue
        piece = _piece(s, rest)
        seen |= piece
        large += len(piece) >= min_area
        if large >= 2:
            return True
    return False

"""Whether closing a few tiles sends a hero the long way round: the open tiles beside the
cut that joined one another through it must still join one another close by."""

from collections.abc import Callable, Iterable

from vcmi_mapgen.core.grid.reach import STEPS8, reach
from vcmi_mapgen.core.model import Tile

MARGIN = 2


def detours(cut: Iterable[Tile], open_at: Callable[[Tile], bool], margin: int = MARGIN) -> bool:
    """Whether closing ``cut`` parts two open tiles beside it that joined, before, through
    the open tiles within ``margin`` steps of it."""
    cut = set(cut)
    box = {
        (x + dx, y + dy)
        for x, y in cut
        for dx in range(-margin, margin + 1)
        for dy in range(-margin, margin + 1)
    }
    before = {t for t in box if open_at(t)}
    after = before - cut
    side = {(x + dx, y + dy) for x, y in cut for dx, dy in STEPS8} & after
    seen: set[Tile] = set()
    for s in sorted(side):
        if s in seen:
            continue
        joined = side & reach(before, [s], STEPS8)
        if not joined <= reach(after, [s], STEPS8):
            return True
        seen |= joined
    return False

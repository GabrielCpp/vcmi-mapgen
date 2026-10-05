"""The flanks of a sprite: each row of its cells has a tile to its left and a tile to its
right. A flank is closed when a hero cannot stand on one of its tiles."""

from collections.abc import Callable, Iterable

from vcmi_mapgen.core.model import Tile


def flank_tiles(cells: Iterable[Tile]) -> tuple[list[Tile], list[Tile]]:
    """The tiles left of each sprite row and the tiles right of it, top row first."""
    rows: dict[int, tuple[int, int]] = {}
    for x, y in cells:
        lo, hi = rows.get(y, (x, x))
        rows[y] = (min(lo, x), max(hi, x))
    left = [(lo - 1, y) for y, (lo, _hi) in sorted(rows.items())]
    right = [(hi + 1, y) for y, (_lo, hi) in sorted(rows.items())]
    return left, right


def closed_flanks(cells: Iterable[Tile], closed: Callable[[Tile], bool]) -> int:
    """How many of the two flanks of a sprite over ``cells`` hold a closed tile."""
    return sum(any(closed(t) for t in side) for side in flank_tiles(cells))

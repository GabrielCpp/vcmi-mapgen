"""Whether a sprite sits snug for its size. A one-tile object sits in a hole or a corner: three
of its sides closed, or two sides that meet. A two-tile object has the tile past its far end,
away from its visit tile, closed. A larger object has a closed tile above the top of its body.
A sprite that is not snug may still be sided: one closed tile beside its body.
A tile is closed when a hero cannot stand on it."""

from collections.abc import Callable

from vcmi_mapgen.core.model import Footprint, Role, Tile

SIZE_CLASSES = (1, 2, 3)

_SIDES = ((0, -1), (1, 0), (0, 1), (-1, 0))


def solid_cells(fp: Footprint, anchor: Tile) -> list[tuple[Tile, Role]]:
    """The cells of ``fp`` at ``anchor`` a hero cannot walk under, with their roles."""
    return [(t, role) for t, role in fp.at(*anchor) if role not in (Role.OVERLAY, Role.APPROACH)]


def size_class(fp: Footprint) -> int:
    """1 or 2 for a body of that many cells, 3 for any larger body."""
    return min(len(solid_cells(fp, (0, 0))), SIZE_CLASSES[-1])


def snug(fp: Footprint, anchor: Tile, closed: Callable[[Tile], bool]) -> bool:
    """Whether a sprite of ``fp`` at ``anchor`` sits snug for its size class."""
    cells = solid_cells(fp, anchor)
    if len(cells) == 1:
        return _nested(cells[0][0], closed)
    if len(cells) == 2:
        return _backed_pair(cells, closed)
    top: dict[int, int] = {}
    for (x, y), _role in cells:
        top[x] = min(y, top.get(x, y))
    return any(closed((x, y - 1)) for x, y in top.items())


def sided(fp: Footprint, anchor: Tile, closed: Callable[[Tile], bool]) -> bool:
    """Whether a sprite of ``fp`` at ``anchor`` has at least one closed side: a closed tile
    beside one of its body cells, outside the body. A tile touching the body only at a
    corner never counts."""
    body = {t for t, _role in solid_cells(fp, anchor)}
    return any(
        (n := (x + dx, y + dy)) not in body and closed(n) for x, y in body for dx, dy in _SIDES
    )


def _nested(t: Tile, closed: Callable[[Tile], bool]) -> bool:
    shut = [closed((t[0] + dx, t[1] + dy)) for dx, dy in _SIDES]
    return sum(shut) >= 3 or any(shut[i] and shut[(i + 1) % 4] for i in range(4))


def _backed_pair(cells: list[tuple[Tile, Role]], closed: Callable[[Tile], bool]) -> bool:
    (a, ra), (b, rb) = cells
    if ra.interactive == rb.interactive:
        return _beyond(a, b, closed) or _beyond(b, a, closed)
    visit, far = (a, b) if ra.interactive else (b, a)
    return _beyond(visit, far, closed)


def _beyond(near: Tile, far: Tile, closed: Callable[[Tile], bool]) -> bool:
    return closed((2 * far[0] - near[0], 2 * far[1] - near[1]))

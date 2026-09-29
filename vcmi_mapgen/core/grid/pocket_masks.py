import collections

from vcmi_mapgen.core.grid.geometry import NB8
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.priors.pocket_masks import PocketMask

ANY, WALL, FREE, GUARD = "A", "X", " ", "G"
SYMBOLS = frozenset((ANY, WALL, FREE, GUARD))

_TRANSFORMS: tuple[tuple[int, int, int, int], ...] = (
    (1, 0, 0, 1),
    (-1, 0, 0, 1),
    (1, 0, 0, -1),
    (-1, 0, 0, -1),
    (0, 1, 1, 0),
    (0, -1, 1, 0),
    (0, 1, -1, 0),
    (0, -1, -1, 0),
)


class PocketMaskError(ValueError):
    pass


def parse_masks(text: str) -> tuple[PocketMask, ...]:
    masks: list[PocketMask] = []
    seen: set[frozenset[tuple[int, int, bool]]] = set()
    names: set[str] = set()
    for name, rows in _blocks(text):
        if name in names:
            raise PocketMaskError(f"{name}: duplicate name")
        names.add(name)
        free, walls = _read(name, rows)
        for tf in _TRANSFORMS:
            f = _turn(tf, free)
            w = _turn(tf, walls)
            key = frozenset({(x, y, True) for x, y in f} | {(x, y, False) for x, y in w})
            if key in seen:
                continue
            seen.add(key)
            masks.append(_mask(name, f, w))
    return tuple(masks)


def _turn(tf: tuple[int, int, int, int], cells: frozenset[Tile]) -> frozenset[Tile]:
    a, b, c, d = tf
    return frozenset((a * x + b * y, c * x + d * y) for x, y in cells)


def _blocks(text: str) -> list[tuple[str, list[str]]]:
    blocks: list[list[str]] = [[]]
    for line in text.splitlines():
        if line.strip():
            blocks[-1].append(line)
        elif blocks[-1]:
            blocks.append([])
    return [(b[0].strip(), b[1:]) for b in blocks if b]


def _read(name: str, rows: list[str]) -> tuple[frozenset[Tile], frozenset[Tile]]:
    if not rows or len({len(r) for r in rows}) != 1:
        raise PocketMaskError(f"{name}: rows must all have the same width")
    grid = {(x, y): c for y, r in enumerate(rows) for x, c in enumerate(r)}
    if bad := {c for c in grid.values() if c not in SYMBOLS}:
        raise PocketMaskError(f"{name}: unknown symbols {sorted(bad)}")
    guards = [t for t, c in grid.items() if c == GUARD]
    if len(guards) != 1:
        raise PocketMaskError(f"{name}: needs exactly one {GUARD}")
    (gx, gy) = g = guards[0]
    free = {t for t, c in grid.items() if c == FREE}
    if not free:
        raise PocketMaskError(f"{name}: needs at least one free tile")
    for x, y in sorted(free):
        for dx, dy in NB8:
            nx, ny = x + dx, y + dy
            if grid.get((nx, ny), ANY) == ANY and max(abs(nx - gx), abs(ny - gy)) > 1:
                raise PocketMaskError(f"{name}: free tile {(x, y)} is not closed off")
    if _reached_from(g, free) != free:
        raise PocketMaskError(f"{name}: every free tile must be reachable from {GUARD}")
    walls = {t for t, c in grid.items() if c == WALL}
    return (
        frozenset((x - gx, y - gy) for x, y in free),
        frozenset((x - gx, y - gy) for x, y in walls),
    )


def _reached_from(g: Tile, free: set[Tile]) -> set[Tile]:
    seen: set[Tile] = set()
    q = collections.deque([g])
    while q:
        x, y = q.popleft()
        for dx, dy in NB8:
            t = (x + dx, y + dy)
            if t in free and t not in seen:
                seen.add(t)
                q.append(t)
    return seen


def _mask(name: str, free: frozenset[Tile], walls: frozenset[Tile]) -> PocketMask:
    cells = sorted(
        [(x, y, True) for x, y in free] + [(x, y, False) for x, y in walls],
        key=lambda c: (max(abs(c[0]), abs(c[1])), c),
    )
    walls_by_guard = sum(1 for dx, dy in NB8 if (dx, dy) in walls)
    return PocketMask(name, tuple(cells), free, walls_by_guard)

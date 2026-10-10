# pyright: reportAny=false

import heapq
import math
from typing import NamedTuple

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.jit import njit

AROUND = 3
DIAGONAL = math.sqrt(2)
SLACK = 1e-9
STEPS = tuple(
    (dx, dy, DIAGONAL if dx and dy else 1.0) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy
)


class Grid(NamedTuple):
    """The route map flattened to one array per field, a tile at ``(level * size + y) * size +
    x``. The jumps from a tile land on ``jump_to[jump_at[tile] : jump_at[tile + 1]]``."""

    size: int
    cost: NDArray[np.float64]
    open: NDArray[np.bool_]
    water: NDArray[np.bool_]
    guard: NDArray[np.int64]
    gate: NDArray[np.int64]
    tent: NDArray[np.int64]
    dock: NDArray[np.bool_]
    jump_at: NDArray[np.int64]
    jump_to: NDArray[np.int64]


class Ceilings(NamedTuple):
    """The guard ceilings of an effort map, the best travel days under each, one row per
    ceiling, and the days to beat a guard of each level."""

    levels: NDArray[np.int64]
    days: NDArray[np.float64]
    toll: NDArray[np.int64]


class _Run(NamedTuple):
    best: NDArray[np.float64]
    ceiling: int
    colour: int


@njit
def _passable(grid: Grid, run: _Run, tile: int, key: int) -> bool:
    if not grid.open[tile] or grid.guard[tile] > run.ceiling:
        return False
    return grid.gate[tile] < 0 or (key == 1 and grid.gate[tile] == run.colour)


@njit
def _arrive(grid: Grid, at: tuple[float, int, int], tile: int, scale: float) -> float:
    days, here, boat = at
    if boat == int(grid.water[tile]):
        return days + grid.cost[here] * scale
    if boat == 1 or grid.dock[tile]:
        return math.floor(days + SLACK) + 1.0
    return -1.0


@njit
def _reach(
    grid: Grid, run: _Run, heap: list[tuple[float, int]], at: tuple[float, int, int]
) -> None:
    days, tile, key = at
    if grid.tent[tile] == run.colour:
        key = 1
    state = tile * 4 + key * 2 + int(grid.water[tile])
    if days < run.best[state]:
        run.best[state] = days
        heapq.heappush(heap, (days, state))


@njit
def _expand(grid: Grid, run: _Run, heap: list[tuple[float, int]], days: float, state: int) -> None:
    tile, key, boat = state >> 2, (state >> 1) & 1, state & 1
    rest, x = divmod(tile, grid.size)
    base, y = divmod(rest, grid.size)
    for dx, dy, scale in STEPS:
        nx, ny = x + dx, y + dy
        if not (0 <= nx < grid.size and 0 <= ny < grid.size):
            continue
        n = (base * grid.size + ny) * grid.size + nx
        if not _passable(grid, run, n, key):
            continue
        arrive = _arrive(grid, (days, tile, boat), n, scale)
        if arrive < 0.0:
            continue
        _reach(grid, run, heap, (arrive, n, key))
        for j in range(grid.jump_at[n], grid.jump_at[n + 1]):
            far = grid.jump_to[j]
            if grid.guard[far] <= run.ceiling:
                _reach(grid, run, heap, (arrive, far, key))


@njit
def search(grid: Grid, homes: NDArray[np.int64], ceiling: int, colour: int) -> NDArray[np.float64]:
    """The best travel days from ``homes`` to every search state, four per tile for the key
    and the boat. The search never enters a tile a guard stronger than ``ceiling`` covers. It
    passes the gates of ``colour`` once it reaches that colour's tent."""
    tiles = grid.cost.shape[0]
    run = _Run(np.full(tiles * 4, np.inf), ceiling, colour)
    heap = [(0.0, homes[0] * 4)]
    _ = heap.pop()
    for tile in homes:
        run.best[tile * 4] = 0.0
        heap.append((0.0, tile * 4))
    heapq.heapify(heap)
    while heap:
        days, state = heapq.heappop(heap)
        if days <= run.best[state]:
            _expand(grid, run, heap, days, state)
    return run.best


@njit
def _window_seeds(
    grid: Grid, days: NDArray[np.float64], tile: int, blocked: NDArray[np.bool_]
) -> tuple[NDArray[np.float64], list[tuple[float, int]]]:
    span = 2 * AROUND + 1
    rest, x = divmod(tile, grid.size)
    base, y = divmod(rest, grid.size)
    best = np.full(span * span, np.inf)
    heap = [(0.0, 0)]
    _ = heap.pop()
    for ny in range(max(0, y - AROUND), min(grid.size, y + AROUND + 1)):
        for nx in range(max(0, x - AROUND), min(grid.size, x + AROUND + 1)):
            k = (ny - y + AROUND) * span + nx - x + AROUND
            d = days[(base * grid.size + ny) * grid.size + nx]
            edge = max(abs(nx - x), abs(ny - y)) == AROUND or d <= SLACK
            if edge and not blocked[k] and d < math.inf:
                best[k] = d
                heap.append((d, k))
    heapq.heapify(heap)
    return best, heap


@njit
def _window_shut(grid: Grid, tile: int, shut: NDArray[np.int64]) -> NDArray[np.bool_]:
    span = 2 * AROUND + 1
    rest, x = divmod(tile, grid.size)
    base, y = divmod(rest, grid.size)
    blocked = np.zeros(span * span, dtype=np.bool_)
    for t in shut:
        r, sx = divmod(t, grid.size)
        level, sy = divmod(r, grid.size)
        if level == base and abs(sx - x) <= AROUND and abs(sy - y) <= AROUND:
            blocked[(sy - y + AROUND) * span + sx - x + AROUND] = True
    return blocked


@njit
def _around(
    grid: Grid, days: NDArray[np.float64], ceiling: int, tile: int, shut: NDArray[np.int64]
) -> float:
    """The days to reach ``tile`` once ``shut`` blocks, the tiles within ``AROUND`` steps of
    it walked again under ``ceiling`` from the ``days`` around them."""
    span = 2 * AROUND + 1
    rest, x = divmod(tile, grid.size)
    base, y = divmod(rest, grid.size)
    blocked = _window_shut(grid, tile, shut)
    best, heap = _window_seeds(grid, days, tile, blocked)
    while heap:
        d, k = heapq.heappop(heap)
        if d > best[k]:
            continue
        tx, ty = x - AROUND + k % span, y - AROUND + k // span
        t = (base * grid.size + ty) * grid.size + tx
        for dx, dy, scale in STEPS:
            nx, ny = tx + dx, ty + dy
            if not (0 <= nx < grid.size and 0 <= ny < grid.size):
                continue
            if abs(nx - x) > AROUND or abs(ny - y) > AROUND:
                continue
            m = (ny - y + AROUND) * span + nx - x + AROUND
            n = (base * grid.size + ny) * grid.size + nx
            if blocked[m] or not grid.open[n] or grid.guard[n] > ceiling:
                continue
            if grid.water[n] == grid.water[t]:
                arrive = d + grid.cost[t] * scale
            else:
                arrive = math.floor(d + SLACK) + 1.0
            if arrive < best[m]:
                best[m] = arrive
                heapq.heappush(heap, (arrive, m))
    return best[AROUND * span + AROUND]


@njit
def beside(
    grid: Grid, ceilings: Ceilings, tile: int, least: int, shut: NDArray[np.int64]
) -> tuple[int, int, int]:
    """The cheapest total, guard level and travel days to reach ``tile`` once ``shut``
    blocks, beating a guard of at least ``least`` on the way. The total is -1 when no
    ceiling reaches ``tile``."""
    levels = ceilings.levels
    best: tuple[int, int, int] = (-1, 0, 0)
    for i in range(levels.shape[0]):
        ceiling = int(levels[i])
        if np.any((levels > ceiling) & (levels <= least)):
            continue
        arrive = _around(grid, ceilings.days[i], ceiling, tile, shut)
        if arrive < math.inf:
            guard = max(ceiling, least)
            whole = math.ceil(arrive - SLACK)
            option = (int(ceilings.toll[guard]) + whole, guard, whole)
            if best[0] < 0 or option < best:
                best = option
    return best

"""A quota flood of land: every territory floods outward from its site over 4-connected
land, all at the same share of their area targets, and stops at its target. Land left over
joins the territory that reaches it first, and border tiles then pass from territories over
their share to neighbours under it."""

import heapq
from collections import deque
from collections.abc import Sequence
from typing import cast

import numpy as np
import numpy.typing as npt

from vcmi_mapgen.core.model import Tile

type Mask = npt.NDArray[np.bool_]
type Field = npt.NDArray[np.float64]
type Labels = npt.NDArray[np.int64]

SWAY = 0.5
BALANCE_ROUNDS = 400
RING = ((-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0))
NEIGHBOURS = ((1, 0), (-1, 0), (0, 1), (0, -1))


type Grid = list[list[int]]


def quota_flood(
    land: Mask, sites: Sequence[Tile], targets: Sequence[float], noise: Sequence[Field]
) -> Labels:
    """The territory of each land tile, -1 off land. Territories take turns, the one holding
    the smallest share of its target first, and each takes the free tile on its frontier
    that lies cheapest from its site, entering a tile ``t`` at ``1 + SWAY * noise_i(t)``. A
    territory stops at its target. The land left over is taken by a plain flood from the
    assigned tiles, and land no site touches by the nearest site in a straight line. Border
    tiles then pass from a territory to a neighbour holding a smaller share of its target,
    never a site and never one that cuts its territory in two."""
    h, w = land.shape
    rows = cast("list[list[bool]]", land.tolist())
    label: Grid = [[-1] * w for _ in range(h)]
    _flood(rows, label, sites, targets, noise)
    _spread(rows, label, sites)
    _balance(label, sites, targets)
    return np.asarray(label, dtype=np.int64)


def _flood(
    rows: list[list[bool]],
    label: Grid,
    sites: Sequence[Tile],
    targets: Sequence[float],
    noise: Sequence[Field],
) -> None:
    h, w = len(rows), len(rows[0])
    grids = [cast("list[list[float]]", f.tolist()) for f in noise]
    held = [0] * len(sites)
    edges: list[list[tuple[float, int, int]]] = [[(0.0, y, x)] for x, y in sites]
    turns = [(0.0, i) for i in range(len(sites))]
    heapq.heapify(turns)
    while turns:
        _, i = heapq.heappop(turns)
        edge = edges[i]
        while edge and label[edge[0][1]][edge[0][2]] >= 0:
            _ = heapq.heappop(edge)
        if not edge or held[i] >= targets[i]:
            continue
        cost, y, x = heapq.heappop(edge)
        label[y][x] = i
        held[i] += 1
        for dx, dy in NEIGHBOURS:
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and rows[ny][nx] and label[ny][nx] < 0:
                heapq.heappush(edge, (cost + 1.0 + SWAY * grids[i][ny][nx], ny, nx))
        heapq.heappush(turns, (held[i] / targets[i], i))


def _spread(rows: list[list[bool]], label: Grid, sites: Sequence[Tile]) -> None:
    h, w = len(rows), len(rows[0])
    queue = deque((x, y) for y in range(h) for x in range(w) if label[y][x] >= 0)
    while queue:
        x, y = queue.popleft()
        for dx, dy in NEIGHBOURS:
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and rows[ny][nx] and label[ny][nx] < 0:
                label[ny][nx] = label[y][x]
                queue.append((nx, ny))
    for y in range(h):
        for x in range(w):
            if rows[y][x] and label[y][x] < 0:
                label[y][x] = min(
                    range(len(sites)),
                    key=lambda i: ((sites[i][0] - x) ** 2 + (sites[i][1] - y) ** 2, i),
                )


def _cuts(label: Grid, x: int, y: int) -> bool:
    """Whether taking tile ``(x, y)`` from its territory splits the territory's tiles
    around it into more than one 4-connected group within its 3x3 ring."""
    h, w = len(label), len(label[0])
    mine = label[y][x]
    flags = [
        0 <= x + dx < w and 0 <= y + dy < h and label[y + dy][x + dx] == mine for dx, dy in RING
    ]
    sides = [k for k in range(1, 8, 2) if flags[k]]
    if not sides:
        return True
    reach = {sides[0]}
    stack = [sides[0]]
    while stack:
        k = stack.pop()
        for n in ((k + 1) % 8, (k - 1) % 8):
            if flags[n] and n not in reach and (n % 2 == 1 or k % 2 == 1):
                reach.add(n)
                stack.append(n)
    return not all(k in reach for k in sides)


type Want = tuple[float, float, int, int, int]


def _wants(label: Grid, anchored: set[Tile], share: list[float]) -> list[Want]:
    h, w = len(label), len(label[0])
    wants: list[Want] = []
    for y in range(h):
        for x in range(w):
            j = label[y][x]
            if j < 0 or (x, y) in anchored:
                continue
            for dx, dy in NEIGHBOURS:
                nx, ny = x + dx, y + dy
                i = label[ny][nx] if 0 <= nx < w and 0 <= ny < h else -1
                if i >= 0 and i != j and share[i] < 1.0 and share[j] > share[i]:
                    wants.append((share[i], -share[j], y, x, i))
    wants.sort()
    return wants


def _balance(label: Grid, sites: Sequence[Tile], targets: Sequence[float]) -> None:
    count = [0] * len(sites)
    for row in label:
        for c in row:
            if c >= 0:
                count[c] += 1
    anchored = set(sites)
    for _ in range(BALANCE_ROUNDS):
        share = [count[i] / targets[i] for i in range(len(sites))]
        moved = False
        for _, _, y, x, i in _wants(label, anchored, share):
            j = label[y][x]
            after_gain, after_loss = (count[i] + 1) / targets[i], (count[j] - 1) / targets[j]
            if j == i or count[i] >= targets[i] or after_loss < after_gain or _cuts(label, x, y):
                continue
            label[y][x] = i
            count[i] += 1
            count[j] -= 1
            moved = True
        if not moved:
            break


def cell_areas(label: Labels, cells: int) -> Field:
    """The tile count of each of ``cells`` cells of ``label``."""
    counts = np.zeros(cells, dtype=np.float64)
    for cell in range(cells):
        counts[cell] = float(np.count_nonzero(np.equal(label, cell)))
    return counts


def cell_tiles(label: Labels, cell: int) -> list[Tile]:
    """The ``(x, y)`` tiles of ``cell`` in ``label``, row by row."""
    rows = cast("list[list[int]]", label.tolist())
    return [(x, y) for y, row in enumerate(rows) for x, c in enumerate(row) if c == cell]

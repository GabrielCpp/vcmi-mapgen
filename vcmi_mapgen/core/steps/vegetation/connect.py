# pyright: reportAny=false

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.steps.vegetation.jit import njit

_STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1))
_CLOSED, _OPEN, _WEB = 0, 1, 2


@njit
def _ground(
    solid: NDArray[np.bool_], protm: NDArray[np.bool_], blkcnt: NDArray[np.int32]
) -> NDArray[np.int8]:
    H, W = solid.shape
    ground = np.zeros((H, W), np.int8)
    for y in range(H):
        for x in range(W):
            if not solid[y, x] and blkcnt[y, x] == 0:
                ground[y, x] = _WEB if protm[y, x] else _OPEN
    return ground


@njit
def _reaches_web(
    ground: NDArray[np.int8],
    mark: NDArray[np.int32],
    queue: NDArray[np.int64],
    start: int,
    stamp: int,
) -> bool:
    H, W = ground.shape
    sy, sx = divmod(start, W)
    mark[sy, sx] = stamp
    if ground[sy, sx] == _WEB:
        return True
    head, tail = 0, 1
    queue[0] = start
    while head < tail:
        cy, cx = divmod(queue[head], W)
        head += 1
        for dx, dy in _STEPS:
            mx, my = cx + dx, cy + dy
            if not (0 <= mx < W and 0 <= my < H):
                continue
            if mark[my, mx] == stamp or ground[my, mx] == _CLOSED:
                continue
            if ground[my, mx] == _WEB or mark[my, mx] != 0:
                return True
            mark[my, mx] = stamp
            queue[tail] = my * W + mx
            tail += 1
    return False


@njit
def keeps_connected(
    solid: NDArray[np.bool_],
    protm: NDArray[np.bool_],
    blkcnt: NDArray[np.int32],
    xs: NDArray[np.int64],
    ys: NDArray[np.int64],
) -> bool:
    """Whether every open 4-neighbour of the cells (xs, ys) still reaches the protected web
    once those cells are blocked."""
    H, W = solid.shape
    ground = _ground(solid, protm, blkcnt)
    for k in range(xs.shape[0]):
        ground[ys[k], xs[k]] = _CLOSED
    mark = np.zeros((H, W), np.int32)
    queue = np.empty(H * W, np.int64)
    stamp = 0
    for k in range(xs.shape[0]):
        for dx, dy in _STEPS:
            nx, ny = xs[k] + dx, ys[k] + dy
            if not (0 <= nx < W and 0 <= ny < H):
                continue
            if ground[ny, nx] == _CLOSED or mark[ny, nx] != 0:
                continue
            stamp += 1
            if not _reaches_web(ground, mark, queue, ny * W + nx, stamp):
                return False
    return True


@njit
def frees_connected(
    solid: NDArray[np.bool_],
    protm: NDArray[np.bool_],
    blkcnt: NDArray[np.int32],
    xs: NDArray[np.int64],
    ys: NDArray[np.int64],
) -> bool:
    """Whether every tile freed by removing the cells (xs, ys) reaches the protected web
    through open tiles or other freed tiles."""
    H, W = solid.shape
    ground = _ground(solid, protm, blkcnt)
    freed = np.zeros((H, W), np.bool_)
    for k in range(xs.shape[0]):
        x, y = xs[k], ys[k]
        if blkcnt[y, x] == 1 and not solid[y, x]:
            freed[y, x] = True
            ground[y, x] = _WEB if protm[y, x] else _OPEN
    mark = np.zeros((H, W), np.int32)
    queue = np.empty(H * W, np.int64)
    stamp = 0
    for k in range(xs.shape[0]):
        x, y = xs[k], ys[k]
        if not freed[y, x] or mark[y, x] != 0:
            continue
        stamp += 1
        if not _reaches_web(ground, mark, queue, y * W + x, stamp):
            return False
    return True

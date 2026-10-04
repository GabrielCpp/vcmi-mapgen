"""The cheapest 4-connected path from a set of tiles to another, with a cost per step and a
penalty per turn."""

import heapq
from collections.abc import Callable, Iterable
from collections.abc import Set as AbstractSet

from vcmi_mapgen.core.grid.geometry import NB4
from vcmi_mapgen.core.model import Tile

type StepCost = Callable[[Tile, Tile], float | None]

START = -1


def route(
    sources: Iterable[Tile], targets: AbstractSet[Tile], cost: StepCost, turn: float
) -> list[Tile] | None:
    """The cheapest path from any of ``sources`` to any of ``targets``, from its source to
    its target, or None when no target is reachable. ``cost(u, v)`` is the price of stepping
    from ``u`` to ``v``, None where the step is not allowed, and every change of direction
    adds ``turn``."""
    best: dict[tuple[Tile, int], float] = {}
    prev: dict[tuple[Tile, int], tuple[Tile, int]] = {}
    heap: list[tuple[float, int, Tile, int]] = []
    seq = 0
    for s in sorted(set(sources)):
        best[s, START] = 0.0
        heap.append((0.0, seq, s, START))
        seq += 1
    heapq.heapify(heap)
    while heap:
        d, _, u, k = heapq.heappop(heap)
        if d > best.get((u, k), float("inf")):
            continue
        if u in targets:
            return _unwind(prev, (u, k))
        for j, (dx, dy) in enumerate(NB4):
            v = (u[0] + dx, u[1] + dy)
            c = cost(u, v)
            if c is None:
                continue
            nd = d + c + (turn if k not in (START, j) else 0.0)
            if nd < best.get((v, j), float("inf")):
                best[v, j] = nd
                prev[v, j] = (u, k)
                heapq.heappush(heap, (nd, seq, v, j))
                seq += 1
    return None


def _unwind(prev: dict[tuple[Tile, int], tuple[Tile, int]], state: tuple[Tile, int]) -> list[Tile]:
    path = [state[0]]
    while state in prev:
        state = prev[state]
        path.append(state[0])
    path.reverse()
    return path

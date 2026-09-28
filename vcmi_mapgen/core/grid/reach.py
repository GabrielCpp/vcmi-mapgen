"""The BFS family over tile sets: distances from sources, the set they reach, and the
shortest walk to a goal. A flood fill over tiles in the core goes through here. A search
with its own stop rule, or one over a grid-indexed label array, keeps its own loop."""

import collections
from collections.abc import Container, Iterable, Sequence

from vcmi_mapgen.core.model import Tile

type Steps = Sequence[tuple[int, int]]

STEPS4: Steps = ((1, 0), (-1, 0), (0, 1), (0, -1))
STEPS8: Steps = tuple((dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy)


def distances(
    open_set: Container[Tile], sources: Iterable[Tile], steps: Steps = STEPS4
) -> dict[Tile, int]:
    """Steps from the nearest source to each tile of ``open_set`` the sources reach, in the
    order the search meets them. Every source sits at distance 0, inside ``open_set`` or
    not."""
    d = dict.fromkeys(sources, 0)
    q = collections.deque(d)
    while q:
        cur = q.popleft()
        for dx, dy in steps:
            n = (cur[0] + dx, cur[1] + dy)
            if n in open_set and n not in d:
                d[n] = d[cur] + 1
                q.append(n)
    return d


def reach(open_set: Container[Tile], sources: Iterable[Tile], steps: Steps = STEPS4) -> set[Tile]:
    """The sources and every tile of ``open_set`` they reach."""
    return set(distances(open_set, sources, steps))


def walk(
    sources: Iterable[Tile],
    goal: Container[Tile],
    passable: Container[Tile],
    steps: Steps = STEPS4,
) -> list[Tile]:
    """The shortest walk through ``passable`` from any source to the nearest goal tile,
    goal end first, or an empty list when no goal tile is reachable. The sources need not
    lie in ``passable``."""
    prev: dict[Tile, Tile | None] = dict.fromkeys(sources)
    q = collections.deque(prev)
    while q:
        cur = q.popleft()
        if cur in goal:
            path: list[Tile] = []
            node: Tile | None = cur
            while node is not None:
                path.append(node)
                node = prev[node]
            return path
        for dx, dy in steps:
            n = (cur[0] + dx, cur[1] + dy)
            if n in passable and n not in prev:
                prev[n] = cur
                q.append(n)
    return []


def entry_reach(passable: Container[Tile], entry: Tile) -> set[Tile]:
    """The 4-connected reach from ``entry``. A blocked entry is left out, and the reach
    still spreads through its passable neighbours."""
    out = reach(passable, [entry])
    if entry not in passable:
        out.discard(entry)
    return out

"""The BFS family over tile sets: the 8-connected reach and the 4-connected reach
from one entry tile."""

import collections
from collections.abc import Container

from vcmi_mapgen.core.model import Tile


def bfs8(open_set: Container[Tile], root: Tile) -> set[Tile]:
    seen = {root}
    queue = collections.deque([root])
    while queue:
        x, y = queue.popleft()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                n = (x + dx, y + dy)
                if n in open_set and n not in seen:
                    seen.add(n)
                    queue.append(n)
    return seen


def entry_reach(passable: Container[Tile], entry: Tile) -> set[Tile]:
    reach: set[Tile] = {entry} if entry in passable else set()
    q = [entry]
    while q:
        x, y = q.pop()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if n in passable and n not in reach:
                reach.add(n)
                q.append(n)
    return reach

"""The route net of one zone: the waypoints a hero must reach, the near-straight routes that
join them with the loops a short walk needs, and the open ground each route keeps."""

import heapq
import math
from collections.abc import Collection, Sequence
from collections.abc import Set as AbstractSet
from itertools import combinations

from vcmi_mapgen.core.grid.reach import STEPS8, walk
from vcmi_mapgen.core.model import Tile

STRETCH = 1.4


def _groups(tiles: AbstractSet[Tile]) -> list[list[Tile]]:
    """The 8-connected groups of `tiles`, each sorted, in order of their first tile."""
    seen: set[Tile] = set()
    out: list[list[Tile]] = []
    for t in sorted(tiles):
        if t in seen:
            continue
        group = [t]
        seen.add(t)
        stack = [t]
        while stack:
            x, y = stack.pop()
            for dx, dy in STEPS8:
                n = (x + dx, y + dy)
                if n in tiles and n not in seen:
                    seen.add(n)
                    group.append(n)
                    stack.append(n)
        out.append(sorted(group))
    return out


def _middle(group: Sequence[Tile]) -> Tile:
    mx = sum(x for x, _ in group) / len(group)
    my = sum(y for _, y in group) / len(group)
    return min(group, key=lambda t: ((t[0] - mx) ** 2 + (t[1] - my) ** 2, t))


def ways_in(prot: AbstractSet[Tile], ts: AbstractSet[Tile]) -> set[Tile]:
    """The protected tiles of the zone `ts` on its rim: its entrance bands and its doors,
    taken ground or not."""
    return {(x, y) for x, y in prot & ts if any((x + dx, y + dy) not in ts for dx, dy in STEPS8)}


def waypoints(ways_in: AbstractSet[Tile], room: Collection[Tile], spacing: float) -> list[Tile]:
    """One waypoint at the middle of each 8-connected group of `ways_in`, then the tiles of
    `room` farthest from every waypoint so far, until every tile of `room` lies within
    `spacing` of one. A room with no way in starts from its middle tile."""
    cand = sorted(room)
    if not cand:
        return []
    nodes = [_middle(g) for g in _groups(ways_in)] or [_middle(cand)]
    gap = {t: min((t[0] - n[0]) ** 2 + (t[1] - n[1]) ** 2 for n in nodes) for t in cand}
    s2 = spacing * spacing
    while True:
        best = max(cand, key=lambda t: gap[t])
        if gap[best] < s2:
            return nodes
        nodes.append(best)
        for t in cand:
            gap[t] = min(gap[t], (t[0] - best[0]) ** 2 + (t[1] - best[1]) ** 2)


def _line(a: Tile, b: Tile) -> list[Tile]:
    """The 8-connected straight line from `a` to `b`."""
    n = max(abs(b[0] - a[0]), abs(b[1] - a[1]))
    if n == 0:
        return [a]
    return [
        (round(a[0] + (b[0] - a[0]) * i / n), round(a[1] + (b[1] - a[1]) * i / n))
        for i in range(n + 1)
    ]


def _thick(path: Sequence[Tile], room: AbstractSet[Tile]) -> list[Tile]:
    out = [path[0]]
    for t in path[1:]:
        p = out[-1]
        if t[0] != p[0] and t[1] != p[1]:
            side = next((s for s in ((t[0], p[1]), (p[0], t[1])) if s in room), None)
            if side is not None:
                out.append(side)
        out.append(t)
    return out


def route(a: Tile, b: Tile, room: AbstractSet[Tile]) -> list[Tile]:
    """The spine of the open band from `a` to `b`: the straight line when it stays in
    `room`, else the shortest 8-connected walk through `room`. Empty when `room` does not
    join them."""
    line = _line(a, b)
    if all(t in room for t in line):
        return line
    return walk([a], {b}, room | {a, b}, STEPS8)[::-1]


def _graph_dist(adj: dict[int, dict[int, float]], a: int, b: int) -> float:
    best = {a: 0.0}
    heap = [(0.0, a)]
    while heap:
        d, u = heapq.heappop(heap)
        if u == b:
            return d
        if d > best[u]:
            continue
        for v, w in adj[u].items():
            nd = d + w
            if nd < best.get(v, math.inf):
                best[v] = nd
                heapq.heappush(heap, (nd, v))
    return math.inf


def route_net(nodes: Sequence[Tile], room: AbstractSet[Tile]) -> set[Tile]:
    """The routes that join `nodes` through `room`: each pair in order of distance gets its
    route when the net so far walks it more than STRETCH times the straight line, so the net
    joins every node it can reach and holds the loops a short walk needs."""
    adj: dict[int, dict[int, float]] = {i: {} for i in range(len(nodes))}
    tiles: set[Tile] = set()

    def cheb(i: int, j: int) -> float:
        a, b = nodes[i], nodes[j]
        return max(abs(a[0] - b[0]), abs(a[1] - b[1]))

    for i, j in sorted(combinations(range(len(nodes)), 2), key=lambda p: (cheb(*p), p)):
        if _graph_dist(adj, i, j) <= STRETCH * cheb(i, j):
            continue
        path = route(nodes[i], nodes[j], room)
        if not path:
            continue
        tiles.update(_thick(path, room))
        adj[i][j] = adj[j][i] = float(len(path) - 1)
    return tiles | set(nodes)

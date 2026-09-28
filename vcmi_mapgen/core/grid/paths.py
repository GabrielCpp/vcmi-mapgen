"""Geodesic paths and farthest-point sampling inside a zone's tile set."""

import collections
from collections.abc import Collection, Container, Iterable

from vcmi_mapgen.core.grid.geometry import NB4
from vcmi_mapgen.core.model import Tile

SPACING = (
    6  # farthest-point node spacing for the spanning backbone (bigger -> fewer, fatter corridors)
)


def geodesic_path(a: Tile, b: Tile, ts: Container[Tile]) -> list[Tile]:
    """Shortest 4-connected path a->b staying inside the zone `ts`; [] if unreachable."""
    prev: dict[Tile, Tile | None] = {a: None}
    q = collections.deque([a])
    while q:
        cur = q.popleft()
        if cur == b:
            break
        x, y = cur
        for dx, dy in NB4:
            n = (x + dx, y + dy)
            if n in ts and n not in prev:
                prev[n] = cur
                q.append(n)
    if b not in prev:
        return []
    path: list[Tile] = []
    cur: Tile | None = b
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    return path


def farthest_points(
    ts: Iterable[Tile], seedt: Tile, spacing: int, cand: Collection[Tile] | None = None
) -> list[Tile]:
    """Farthest-point sampling: node tiles spread across the zone so every tile is within ~`spacing`
    of a node. These are the destinations the spanning backbone must reach -> full-zone coverage.
    `cand` restricts where nodes may sit (e.g. interior-only, to keep the backbone off the rim)."""
    nodes = [seedt]
    if cand is None:
        cand = list(ts)
    s2 = spacing * spacing
    while True:
        best: Tile | None = None
        bd = -1
        for t in cand:
            d = min((t[0] - n[0]) ** 2 + (t[1] - n[1]) ** 2 for n in nodes)
            if d > bd:
                bd, best = d, t
        if best is None or bd < s2:
            break
        nodes.append(best)
    return nodes

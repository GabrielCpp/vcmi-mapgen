"""The borders between labelled regions: their tile pairs, the merge of regions split by
neither a barrier nor a guard, the walkable crossings and the adjacency kind."""

import collections
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from vcmi_mapgen.core.grid.components import components
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.reading.ground import Ground

MERGE_BARRIER = 0.5
GATE_WIDTH = 6
GATE_CLUSTERS = 2

type Pair = tuple[int, int]
type Edge = tuple[Tile, Tile]


class AdjacencyKind(StrEnum):
    OPEN = "open"
    GATED = "gated"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class Crossing:
    """One 4-connected cluster of walkable tile pairs across a border. ``width`` is the
    larger count of distinct tiles on either side. ``guarded`` is True when a tile of the
    cluster lies in a guard's zone of control."""

    tiles: frozenset[Tile]
    width: int
    guarded: bool


@dataclass(frozen=True, slots=True)
class _Tally:
    pairs: int
    blocked: int
    guarded: bool

    def __add__(self, other: "_Tally") -> "_Tally":
        return _Tally(
            self.pairs + other.pairs, self.blocked + other.blocked, self.guarded or other.guarded
        )

    @property
    def barrier(self) -> float:
        return self.blocked / self.pairs


def border_pairs(labels: Mapping[Tile, int]) -> dict[Pair, list[Edge]]:
    """Every 4-adjacent tile pair whose labels differ, keyed by the sorted label pair, each
    pair ordered with the lower label's tile first."""
    out: dict[Pair, list[Edge]] = {}
    for (x, y), p in sorted(labels.items()):
        for n in ((x + 1, y), (x, y + 1)):
            q = labels.get(n)
            if q is None or q == p:
                continue
            if p < q:
                out.setdefault((p, q), []).append(((x, y), n))
            else:
                out.setdefault((q, p), []).append((n, (x, y)))
    return out


def barrier_fraction(ground: Ground, edges: Sequence[Edge]) -> float:
    """The share of ``edges`` with a non-walkable tile on either side."""
    return sum(1 for u, v in edges if u not in ground.walk or v not in ground.walk) / len(edges)


def _tally(ground: Ground, edges: Sequence[Edge]) -> _Tally:
    blocked = sum(1 for u, v in edges if u not in ground.walk or v not in ground.walk)
    guarded = any(u in ground.zoc or v in ground.zoc for u, v in edges)
    return _Tally(len(edges), blocked, guarded)


def _root(parent: Mapping[int, int], x: int) -> int:
    while parent[x] != x:
        x = parent[x]
    return x


def _best_merge(
    base: Mapping[Pair, _Tally], parent: Mapping[int, int], towns: Collection[int]
) -> Pair | None:
    groups: dict[Pair, _Tally] = {}
    for (p, q), t in base.items():
        rp, rq = sorted((_root(parent, p), _root(parent, q)))
        if rp != rq:
            groups[(rp, rq)] = groups[(rp, rq)] + t if (rp, rq) in groups else t
    held = {_root(parent, t) for t in towns}
    ok = [
        (t.barrier, pq)
        for pq, t in groups.items()
        if t.barrier < MERGE_BARRIER and not t.guarded and not (pq[0] in held and pq[1] in held)
    ]
    return min(ok)[1] if ok else None


def merge_regions(
    ground: Ground, labels: Mapping[Tile, int], towns: Collection[int]
) -> dict[int, int]:
    """Old label -> new label after merging, round by round, the pair whose border has the
    lowest barrier fraction under ``MERGE_BARRIER``, no tile in a zone of control, and not
    a town on both sides. New labels count from 0 in the sorted order of each region's
    first tile."""
    base = {pq: _tally(ground, edges) for pq, edges in border_pairs(labels).items()}
    parent = {lab: lab for lab in set(labels.values())}
    while (pair := _best_merge(base, parent, towns)) is not None:
        parent[pair[1]] = pair[0]
    first: dict[int, Tile] = {}
    for t, lab in sorted(labels.items()):
        _ = first.setdefault(_root(parent, lab), t)
    order = {root: i for i, root in enumerate(sorted(first, key=lambda r: first[r]))}
    return {lab: order[_root(parent, lab)] for lab in parent}


def crossings(ground: Ground, edges: Sequence[Edge]) -> tuple[Crossing, ...]:
    """The 4-connected clusters of the walkable pairs among ``edges``."""
    walkable = [(u, v) for u, v in edges if u in ground.walk and v in ground.walk]
    comp = components({t for e in walkable for t in e})
    sides: dict[int, tuple[set[Tile], set[Tile]]] = collections.defaultdict(lambda: (set(), set()))
    for u, v in walkable:
        sides[comp[u]][0].add(u)
        sides[comp[u]][1].add(v)
    out: list[Crossing] = []
    for c in sorted(sides):
        lo, hi = sides[c]
        tiles = frozenset(lo | hi)
        out.append(Crossing(tiles, max(len(lo), len(hi)), any(t in ground.zoc for t in tiles)))
    return tuple(out)


def adjacency_kind(cross: Sequence[Crossing]) -> AdjacencyKind:
    """Closed with no crossing, gated with at most ``GATE_CLUSTERS`` crossings each
    narrower than ``GATE_WIDTH``, open otherwise."""
    if not cross:
        return AdjacencyKind.CLOSED
    if len(cross) <= GATE_CLUSTERS and all(c.width < GATE_WIDTH for c in cross):
        return AdjacencyKind.GATED
    return AdjacencyKind.OPEN

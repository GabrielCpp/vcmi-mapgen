"""The kind of every realised place border (map-math 7): closed, gated or open, drawn from
the corpus table p(kind | role pair) once a spanning forest of passable borders keeps every
place reachable."""

import random
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence

from vcmi_mapgen.core.reading.borders import AdjacencyKind
from vcmi_mapgen.core.reading.places import PlaceRole

type Pair = tuple[int, int]

PASSABLE = (AdjacencyKind.GATED, AdjacencyKind.OPEN)
ALL_KINDS = (AdjacencyKind.CLOSED, *PASSABLE)


def kind_weights(
    table: Mapping[str, int], a: PlaceRole, b: PlaceRole
) -> dict[AdjacencyKind, float]:
    """The corpus count of each kind between roles ``a`` and ``b``. Without a single count
    for the pair, the counts pooled over every role pair."""
    lo, hi = sorted((a.value, b.value))
    own = {k: float(table.get(f"{lo}|{hi}|{k.value}", 0)) for k in ALL_KINDS}
    if sum(own.values()) > 0:
        return own
    pooled = dict.fromkeys(ALL_KINDS, 0.0)
    for key, n in table.items():
        pooled[AdjacencyKind(key.rsplit("|", 1)[1])] += n
    return pooled


def draw_kind(
    rng: random.Random, weights: Mapping[AdjacencyKind, float], allowed: Sequence[AdjacencyKind]
) -> AdjacencyKind:
    """One kind among ``allowed`` drawn by ``weights``, gated when none has weight. One draw
    of ``rng`` when some has weight."""
    w = [weights.get(k, 0.0) for k in allowed]
    if sum(w) <= 0:
        return AdjacencyKind.GATED
    return rng.choices(allowed, w)[0]


def _root(parent: dict[int, int], x: int) -> int:
    while parent.setdefault(x, x) != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def spanning_forest(
    edges: Iterable[Pair],
    planned: Collection[Pair],
    weight: Callable[[Pair], float],
    rng: random.Random,
) -> frozenset[Pair]:
    """A spanning forest of ``edges``: Kruskal over the planned edges first, then the
    others, each group in a weighted random order where an edge with a larger ``weight``
    tends to come first and an edge of weight 0 comes last. One draw of ``rng`` per edge."""
    keyed: list[tuple[bool, float, Pair]] = []
    for e in sorted(edges):
        w = weight(e)
        u = rng.random()
        keyed.append((e not in planned, -(u ** (1.0 / w)) if w > 0 else 0.0, e))
    parent: dict[int, int] = {}
    out: set[Pair] = set()
    for _late, _key, (p, q) in sorted(keyed):
        rp, rq = _root(parent, p), _root(parent, q)
        if rp != rq:
            parent[rq] = rp
            out.add((p, q))
    return frozenset(out)


def draw_kinds(
    roles: Mapping[int, PlaceRole],
    realised: Iterable[Pair],
    planned: Collection[Pair],
    table: Mapping[str, int],
    rng: random.Random,
) -> dict[Pair, AdjacencyKind]:
    """The kind of every realised pair. A spanning forest of the realised pairs, planned
    pairs first and each weighted by how often the corpus leaves its role pair passable,
    draws gated or open. Every other planned pair draws from the whole table, and every
    other unplanned pair is closed."""
    pairs = sorted(realised)

    def weights(e: Pair) -> dict[AdjacencyKind, float]:
        return kind_weights(table, roles[e[0]], roles[e[1]])

    def passable(e: Pair) -> float:
        w = weights(e)
        total = sum(w.values())
        return sum(w[k] for k in PASSABLE) / total if total > 0 else 1.0

    span = spanning_forest(pairs, planned, passable, rng)
    kinds: dict[Pair, AdjacencyKind] = {}
    for e in pairs:
        if e in span:
            kinds[e] = draw_kind(rng, weights(e), PASSABLE)
        elif e in planned:
            kinds[e] = draw_kind(rng, weights(e), ALL_KINDS)
        else:
            kinds[e] = AdjacencyKind.CLOSED
    return kinds

"""The places terrain's road layer (map-math 5.4): a greedy forest of legs from each home's
town through the planned passages toward its neighbouring places and their sites, laid on
walkable tiles only and drawn against the corpus road statistics."""

import collections
import heapq
import statistics
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from typing import final

from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.model.road import Road
from vcmi_mapgen.core.priors.places import RoadStats
from vcmi_mapgen.core.reading.borders import AdjacencyKind
from vcmi_mapgen.core.steps.roads.layer import RoadLevel
from vcmi_mapgen.core.steps.roads.route import StepCost, route

TURN = 0.5
PENALTY = 2.0
SHARE = 0.1
RATE = 0.25
MIN_RATE = 0.01
STUB = 4

type Pair = tuple[int, int]


@dataclass(frozen=True, slots=True)
class RoadRules:
    """What the layer reads from the corpus. A step onto its place's dominant terrain costs
    1 and any other step ``penalty``, and a turn costs ``turn``. ``share`` is the road tiles
    per walkable tile. ``rates`` holds the chance a road crosses a passable pair by
    ``"roleA|roleB|kind"`` and ``rate`` the chance for a key ``rates`` lacks."""

    penalty: float = PENALTY
    turn: float = TURN
    share: float = SHARE
    rates: Mapping[str, float] = field(default_factory=dict[str, float])
    rate: float = RATE


def _odds(hit_total: tuple[int, int]) -> float | None:
    hit, total = hit_total
    if not 0 < hit < total:
        return None
    return hit / (total - hit)


def rules_of(stats: RoadStats) -> RoadRules:
    """The rules ``stats`` implies: the odds ratio of a road tile on its place's dominant
    against any land tile as the penalty, the median road share of the levels with a home
    and a road and the crossing rate of every passable key."""
    on, land = _odds(stats.on_dominant), _odds(stats.land_dominant)
    penalty = max(1.0, on / land) if on is not None and land is not None else PENALTY
    shares = [c.road / c.walk for c in stats.counts if c.road and c.homes and c.walk]
    passable = {
        k: v for k, v in stats.crossed.items() if not k.endswith(f"|{AdjacencyKind.CLOSED}")
    }
    hit = sum(h for h, _ in passable.values())
    total = sum(t for _, t in passable.values())
    return RoadRules(
        penalty=penalty,
        share=statistics.median(shares) if shares else SHARE,
        rates={k: h / t for k, (h, t) in passable.items() if t},
        rate=hit / total if total else RATE,
    )


def gates(level: RoadLevel) -> dict[Pair, frozenset[Tile]]:
    """The band tiles of every passage, by (the place they lie in, the place across)."""
    out: dict[Pair, set[Tile]] = collections.defaultdict(set)
    for p, entrances in level.passages.entrances.items():
        for e in entrances:
            out[p, e.other] |= e.band
    return {k: frozenset(v) for k, v in out.items()}


def crosses(level: RoadLevel, gate: Mapping[Pair, AbstractSet[Tile]], u: Tile, v: Tile) -> bool:
    """Whether a road may step from ``u`` to ``v`` across the border of their places: the
    pair is realised, not closed, and the step is open or leaves or enters a passage band."""
    a, b = level.label[u[1]][u[0]], level.label[v[1]][v[0]]
    pair = (min(a, b), max(a, b))
    kind = level.kinds.get(pair)
    if kind is None or kind == AdjacencyKind.CLOSED:
        return False
    return (
        pair in level.passages.open_pairs or u in gate.get((a, b), ()) or v in gate.get((b, a), ())
    )


def step_cost(
    level: RoadLevel,
    rules: RoadRules,
    gate: Mapping[Pair, AbstractSet[Tile]],
    allowed: AbstractSet[int],
) -> StepCost:
    """The price of a road step inside the places ``allowed``, None off the walkable tiles
    or across a border no passage opens."""

    def cost(u: Tile, v: Tile) -> float | None:
        if v not in level.walk:
            return None
        b = level.label[v[1]][v[0]]
        if b not in allowed:
            return None
        if level.label[u[1]][u[0]] != b and not crosses(level, gate, u, v):
            return None
        return 1.0 if level.terrain[v[1]][v[0]] == level.places[b].dominant else rules.penalty

    return cost


def centres(level: RoadLevel) -> dict[int, Tile]:
    """Each place's walkable tile nearest the mean of its walkable tiles."""
    tiles: dict[int, list[Tile]] = collections.defaultdict(list)
    for t in sorted(level.walk):
        p = level.label[t[1]][t[0]]
        if p in level.places:
            tiles[p].append(t)
    out: dict[int, Tile] = {}
    for p, ts in tiles.items():
        mx = sum(x for x, _ in ts) / len(ts)
        my = sum(y for _, y in ts) / len(ts)
        out[p] = min(ts, key=lambda t: ((t[0] - mx) ** 2 + (t[1] - my) ** 2, t))
    return out


@dataclass
class _Net:
    level: RoadLevel
    rules: RoadRules
    gate: Mapping[Pair, frozenset[Tile]]
    nbrs: Mapping[int, Sequence[int]]
    centre: Mapping[int, Tile]
    roads: dict[Tile, Road] = field(default_factory=dict[Tile, Road])
    owner: dict[int, int] = field(default_factory=dict[int, int])

    def place(self, t: Tile) -> int:
        return self.level.label[t[1]][t[0]]

    def in_place(self, p: int) -> list[Tile]:
        return [t for t in self.roads if self.place(t) == p]

    def leg(
        self, sources: Sequence[Tile], targets: AbstractSet[Tile], allowed: AbstractSet[int]
    ) -> list[Tile] | None:
        cost = step_cost(self.level, self.rules, self.gate, allowed)
        return route(sources, targets, cost, self.rules.turn)

    def fresh(self, path: Sequence[Tile]) -> int:
        return sum(1 for t in path if t not in self.roads)

    def lay(self, path: Sequence[Tile]) -> int:
        new = self.fresh(path)
        for t in path:
            _ = self.roads.setdefault(t, self.level.surface)
        return new

    def rate(self, p: int, q: int) -> float:
        a, b = sorted((self.level.places[p].role.value, self.level.places[q].role.value))
        kind = self.level.kinds[min(p, q), max(p, q)]
        return self.rules.rates.get(f"{a}|{b}|{kind.value}", self.rules.rate)


def _targets(net: _Net, p: int) -> list[Tile]:
    towns = [t for h, t in net.level.homes if h == p]
    sites = towns + [s for s in net.level.sites.get(p, ()) if s in net.level.walk]
    if sites:
        return sites
    return [net.centre[p]] if p in net.centre else []


def _visit(net: _Net, p: int, budget: float, spent: int) -> int:
    for i, site in enumerate(_targets(net, p)):
        if site in net.roads:
            continue
        path = net.leg(net.in_place(p), {site}, {p})
        if path is not None and (i == 0 or spent + net.fresh(path) <= budget):
            spent += net.lay(path)
    return spent


type Crossing = tuple[float, int, int, list[Tile]]


def _crossings(net: _Net, p: int, home: int) -> list[Crossing]:
    """Each leg from ``p`` across a passable border into a place no road of ``home``
    reaches, priced at its new tiles over the corpus crossing rate of the pair. A leg into
    a place another home's road reaches ends on that road."""
    out: list[Crossing] = []
    sources = net.in_place(p)
    for q in net.nbrs.get(p, ()):
        if net.owner.get(q) == home:
            continue
        targets = (
            set(net.in_place(q))
            if q in net.owner
            else {t for t in net.level.walk if net.place(t) == q}
        )
        path = net.leg(sources, targets, {p, q}) if targets else None
        if path is not None:
            out.append((net.fresh(path) / max(net.rate(p, q), MIN_RATE), q, p, path))
    return out


def _stub(net: _Net, home: int, approach: Tile) -> None:
    if len(net.in_place(home)) > 1:
        return
    far = {
        t
        for t in net.level.walk
        if net.place(t) == home and max(abs(t[0] - approach[0]), abs(t[1] - approach[1])) >= STUB
    }
    path = net.leg([approach], far, {home})
    if path is not None:
        _ = net.lay(path)


def _home(net: _Net, index: int, home: int, approach: Tile, budget: float) -> None:
    _ = net.lay([approach])
    _ = net.owner.setdefault(home, index)
    spent = _visit(net, home, budget, 0)
    heap = _crossings(net, home, index)
    heapq.heapify(heap)
    first = True
    while heap:
        _, q, _, path = heapq.heappop(heap)
        if net.owner.get(q) == index:
            continue
        if not first and spent + net.fresh(path) > budget:
            continue
        first = False
        spent += net.lay(path)
        if q in net.owner:
            continue
        net.owner[q] = index
        spent = _visit(net, q, budget, spent)
        for c in _crossings(net, q, index):
            heapq.heappush(heap, c)
    _stub(net, home, approach)


def lay_network(level: RoadLevel, rules: RoadRules) -> dict[Tile, Road]:
    """The road surface of every road tile of ``level``. Each home in turn grows from its
    town. Every place it reaches gets a leg to each of its sites, a player town first, or to
    its centre when it has none. The home then crosses the passable border whose leg is
    cheapest for the corpus crossing rate of its pair, the first always and the rest while
    the home has road tiles left of its share. A leg into a place another home reached
    joins that home's road and goes no further."""
    passable = [pq for pq, kind in level.kinds.items() if kind != AdjacencyKind.CLOSED]
    nbrs: dict[int, list[int]] = collections.defaultdict(list)
    for p, q in sorted(passable):
        nbrs[p].append(q)
        nbrs[q].append(p)
    net = _Net(
        level,
        rules,
        gates(level),
        {p: sorted(qs) for p, qs in nbrs.items()},
        centres(level),
    )
    budget = rules.share * len(level.walk) / max(1, len(level.homes))
    for index, (home, approach) in enumerate(level.homes):
        _home(net, index, home, approach, budget)
    return net.roads


@final
class PassageRoads:
    """The places terrain's layer: the greedy forest of ``lay_network``."""

    def lay(self, stats: RoadStats, level: RoadLevel) -> Mapping[Tile, Road]:
        return lay_network(level, rules_of(stats))

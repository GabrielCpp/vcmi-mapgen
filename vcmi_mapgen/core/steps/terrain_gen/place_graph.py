"""The place graph a places map starts from (map-math 4.1): how many places, each one's
role, owner and target size, and which places border which."""

import collections
import math
import random
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.priors.places import PlaceCount, PlaceStats
from vcmi_mapgen.core.reading.places import PlaceRole

MIN_PLACE_AREA = 60
"""Every place must be able to reach this many tiles, which caps the place count."""

SIZE_FLOOR = 30
"""No place is planned smaller than this."""

HOME_FLOOR = 150
"""No home is planned smaller than this, the area a player town needs."""

NEAREST_RECORDS = 5
DEGREE_WEIGHT = 0.5
SWEEPS = 40

type Edge = tuple[int, int]


@dataclass(frozen=True, slots=True)
class PlaceGraph:
    """Place ``i`` has ``roles[i]``, ``owners[i]`` (the player of a home, else None) and a
    target size of ``sizes[i]`` tiles. ``edges`` holds each bordering pair ``(a, b)``,
    ``a < b``."""

    roles: tuple[PlaceRole, ...]
    owners: tuple[int | None, ...]
    sizes: tuple[int, ...]
    edges: frozenset[Edge]


def place_count(counts: Sequence[PlaceCount], players: int, land: int, rng: random.Random) -> int:
    """A corpus place count for a map of ``players`` and ``land`` tiles. The record is drawn
    among the ones with the nearest player count whose land is closest, and its count is
    scaled by land over its land. The count leaves room for a distinct neighbour per home
    and lets every place reach ``MIN_PLACE_AREA`` tiles."""
    best = min(abs(c.players - players) for c in counts)
    group = sorted(
        (c for c in counts if abs(c.players - players) == best),
        key=lambda c: (abs(math.log(c.land / land)), c.places, c.land),
    )
    rec = rng.choice(group[:NEAREST_RECORDS])
    n = round(rec.places * land / rec.land)
    lo = 2 * players + 1
    return max(lo, min(n, land // MIN_PLACE_AREA))


def draw_roles(stats: PlaceStats, n: int, players: int, rng: random.Random) -> list[PlaceRole]:
    """One home per player first, then roles drawn from the corpus marginal of the others."""
    others = [r for r in PlaceRole if r != PlaceRole.HOME and stats.rel_size.get(r.value)]
    weights = [len(stats.rel_size[r.value]) for r in others]
    return [PlaceRole.HOME] * players + rng.choices(others, weights, k=n - players)


def draw_sizes(
    stats: PlaceStats, roles: Sequence[PlaceRole], land: int, rng: random.Random
) -> list[int]:
    """Each place's share drawn from its role's corpus size fractions, renormalised to the
    land, floored at ``SIZE_FLOOR`` and a home at ``HOME_FLOOR``."""
    shares = [rng.choice(stats.rel_size[r.value]) for r in roles]
    total = sum(shares)
    sizes = [max(SIZE_FLOOR, round(s * land / total)) for s in shares]
    return [
        max(HOME_FLOOR, s) if r == PlaceRole.HOME else s for s, r in zip(sizes, roles, strict=True)
    ]


def pair_affinity(stats: PlaceStats) -> dict[tuple[PlaceRole, PlaceRole], float]:
    """The log ratio of how often two roles border in the corpus, over every kind, to how
    often they would if borders paired roles at random."""
    pair: collections.Counter[tuple[str, str]] = collections.Counter()
    for key, count in stats.adjacency.items():
        a, b, _ = key.split("|")
        pair[min(a, b), max(a, b)] += count
    total = sum(pair.values()) or 1
    ends: collections.Counter[str] = collections.Counter()
    for (a, b), count in pair.items():
        ends[a] += count
        ends[b] += count
    out: dict[tuple[PlaceRole, PlaceRole], float] = {}
    for ra in PlaceRole:
        for rb in PlaceRole:
            a, b = min(ra.value, rb.value), max(ra.value, rb.value)
            ma, mb = (ends[a] + 0.5) / (2 * total), (ends[b] + 0.5) / (2 * total)
            expected = ma * mb * (1 if a == b else 2)
            out[ra, rb] = math.log((pair[a, b] + 0.5) / total / expected)
    return out


def mean_degrees(stats: PlaceStats) -> dict[PlaceRole, float]:
    """The corpus mean degree of each role, 1 for a role the corpus never saw."""
    return {
        r: statistics.fmean(stats.degree[r.value]) if stats.degree.get(r.value) else 1.0
        for r in PlaceRole
    }


def spanning_tree(roles: Sequence[PlaceRole], rng: random.Random) -> set[Edge]:
    """A random tree over the places in which every home hangs off its own non-home."""
    hubs = [i for i, r in enumerate(roles) if r != PlaceRole.HOME]
    homes = [i for i, r in enumerate(roles) if r == PlaceRole.HOME]
    rng.shuffle(hubs)
    edges: set[Edge] = set()
    for k in range(1, len(hubs)):
        j = hubs[rng.randrange(k)]
        edges.add((min(hubs[k], j), max(hubs[k], j)))
    for h, j in zip(homes, rng.sample(hubs, len(homes)), strict=True):
        edges.add((min(h, j), max(h, j)))
    return edges


def _neighbours(n: int, edges: set[Edge]) -> list[set[int]]:
    nbr: list[set[int]] = [set() for _ in range(n)]
    for a, b in edges:
        nbr[a].add(b)
        nbr[b].add(a)
    return nbr


def _still_joined(nbr: Sequence[set[int]], a: int, b: int) -> bool:
    seen = {a}
    queue = collections.deque([a])
    while queue:
        u = queue.popleft()
        for v in nbr[u]:
            if (u, v) in ((a, b), (b, a)) or v in seen:
                continue
            if v == b:
                return True
            seen.add(v)
            queue.append(v)
    return False


def _homes_apart(roles: Sequence[PlaceRole], nbr: Sequence[set[int]], a: int, b: int) -> bool:
    """Whether adding ``(a, b)`` keeps every two homes off one edge and off a shared
    neighbour."""
    home = PlaceRole.HOME
    if roles[a] == home and roles[b] == home:
        return False
    for u, v in ((a, b), (b, a)):
        if roles[u] == home and any(roles[w] == home for w in nbr[v]):
            return False
    return True


@dataclass(frozen=True, slots=True)
class _Energy:
    roles: Sequence[PlaceRole]
    affinity: Mapping[tuple[PlaceRole, PlaceRole], float]
    degree: Mapping[PlaceRole, float]

    def toggle(self, nbr: Sequence[set[int]], a: int, b: int, add: bool) -> float:
        step = 1 if add else -1
        out = -step * self.affinity[self.roles[a], self.roles[b]]
        for u in (a, b):
            mu = self.degree[self.roles[u]]
            d = len(nbr[u])
            out += DEGREE_WEIGHT * ((d + step - mu) ** 2 - (d - mu) ** 2)
        return out


def walk_edges(
    roles: Sequence[PlaceRole], stats: PlaceStats, edges: set[Edge], rng: random.Random
) -> set[Edge]:
    """A short Metropolis walk over edge sets from ``edges``. Energy is minus the role-pair
    affinity of every edge plus a penalty on each place's degree away from its role's
    corpus mean. A move keeps the graph connected and the homes apart."""
    n = len(roles)
    energy = _Energy(roles, pair_affinity(stats), mean_degrees(stats))
    nbr = _neighbours(n, edges)
    out = set(edges)
    for _ in range(SWEEPS * n):
        a, b = sorted(rng.sample(range(n), 2))
        add = (a, b) not in out
        if add and not _homes_apart(roles, nbr, a, b):
            continue
        if not add and not _still_joined(nbr, a, b):
            continue
        d_e = energy.toggle(nbr, a, b, add)
        if d_e > 0 and rng.random() >= math.exp(-d_e):
            continue
        if add:
            out.add((a, b))
            nbr[a].add(b)
            nbr[b].add(a)
        else:
            out.discard((a, b))
            nbr[a].discard(b)
            nbr[b].discard(a)
    return out


def draw_graph(stats: PlaceStats, players: int, land: int, rng: random.Random) -> PlaceGraph:
    """The place graph of a level with ``land`` tiles and ``players`` homes."""
    n = place_count(stats.counts, players, land, rng)
    roles = draw_roles(stats, n, players, rng)
    sizes = draw_sizes(stats, roles, land, rng)
    edges = walk_edges(roles, stats, spanning_tree(roles, rng), rng)
    owners = tuple(i if r == PlaceRole.HOME else None for i, r in enumerate(roles))
    return PlaceGraph(tuple(roles), owners, tuple(sizes), frozenset(edges))

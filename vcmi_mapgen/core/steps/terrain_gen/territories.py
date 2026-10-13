"""The territories of a place map: a territory count drawn from the corpus maps nearest it,
each home with a corpus-drawn number of its neighbours, the other places grouped into the
neutral territories the count leaves, and the doors that join them. A door goes on every
touching pair of territories more doors apart than ``MAX_HOP`` or not joined at all. A
Subterranean Gate counts as a door for the hops, so the other level's territories join the
count through ``Across``. Every border between two territories without a door is walled,
the wall as wide as ``wall_width`` gives for the doors between them."""

import collections
import math
import random
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.model import Entrance
from vcmi_mapgen.core.planning.entrances import Passages
from vcmi_mapgen.core.priors.territories import TerritoryCount
from vcmi_mapgen.core.reading.borders import AdjacencyKind
from vcmi_mapgen.core.reading.territories import hop_counts
from vcmi_mapgen.core.steps.terrain_gen.border_kinds import spanning_forest
from vcmi_mapgen.core.steps.terrain_gen.place_graph import NEAREST_RECORDS
from vcmi_mapgen.core.steps.terrain_gen.result import PlannedDoor, TerritoryPlan

type Pair = tuple[int, int]

MAX_DOORS = 2
MAX_HOP = 2
LAND_BAND = 2.0
WALL_WIDTHS = ((1, 72), (3, 24), (4, 18))
"""The least width and the map side per extra tile of a wall between two territories one
door apart, two doors apart, and three or more apart or cut off. Measured on the corpus:
territories a door joins sit 3 tiles apart at the median, and the walled pairs sit at least
4 to 6 tiles apart at the first quartile at every map side."""


@dataclass(frozen=True, slots=True)
class Across:
    """The other level as hop links: each gate as the zone it opens on this level and the
    territory it opens on the other, and the territory pairs the other level's doors join.
    A gate counts as one door hop. Gates never count in a level's loops."""

    gates: tuple[Pair, ...] = ()
    doors: frozenset[Pair] = frozenset()

    def links(self, territory: Sequence[int]) -> set[Pair]:
        """The links over one numbering: this level's territories by ``territory``, then
        the other level's after them."""
        base = max(territory, default=-1) + 1
        out = {(territory[z], base + t) for z, t in self.gates}
        return out | {(base + a, base + b) for a, b in self.doors}


def _neighbours(edges: Iterable[Pair]) -> dict[int, set[int]]:
    out: dict[int, set[int]] = collections.defaultdict(set)
    for a, b in edges:
        out[a].add(b)
        out[b].add(a)
    return out


def draw_count(spread: Sequence[int], rng: random.Random) -> int:
    """One count drawn from the positive values of ``spread``, 1 when it has none."""
    counts = [n for n in spread if n > 0]
    return rng.choice(counts) if counts else 1


def group_neutral(
    places: Iterable[int], edges: Iterable[Pair], spread: Sequence[int], rng: random.Random
) -> list[list[int]]:
    """``places`` grouped into territories. Each grows from the lowest place still free, by
    random steps over ``edges`` to free places, to a count drawn from ``spread``."""
    free = set(places)
    nbr = _neighbours(edges)
    groups: list[list[int]] = []
    for start in sorted(free):
        if start not in free:
            continue
        size = draw_count(spread, rng)
        free.discard(start)
        group = [start]
        while len(group) < size:
            frontier = sorted({n for p in group for n in nbr[p] if n in free})
            if not frontier:
                break
            pick = rng.choice(frontier)
            free.discard(pick)
            group.append(pick)
        groups.append(group)
    return groups


def draw_partition(
    owners: Sequence[int | None],
    edges: Collection[Pair],
    player_zones: Sequence[int],
    territories: int,
    rng: random.Random,
) -> tuple[int, ...]:
    """The territory of each place, where ``owners[p]`` is the player place ``p`` is home
    to. Each home in place order takes itself and a random set of its neighbours over
    ``edges``, a count drawn from ``player_zones`` in all, clamped to the neighbours it
    has. The other places group into neutral territories of one size, the size that splits
    them into the territories the homes leave of ``territories``."""
    nbr = _neighbours(edges)
    territory: dict[int, int] = {}
    homes = [p for p, owner in enumerate(owners) if owner is not None]
    for t, home in enumerate(homes):
        near = sorted(nbr[home])
        if home in territory or any(n in territory for n in near):
            raise ValueError(f"home {home} shares a neighbour with another home")
        k = min(draw_count(player_zones, rng), 1 + len(near))
        for p in (home, *rng.sample(near, k - 1)):
            territory[p] = t
    rest = [p for p in range(len(owners)) if p not in territory]
    inner = [(a, b) for a, b in sorted(edges) if a not in territory and b not in territory]
    spread = neutral_spread(len(rest), territories, len(homes))
    for t, group in enumerate(group_neutral(rest, inner, spread, rng), len(homes)):
        for p in group:
            territory[p] = t
    return tuple(territory[p] for p in range(len(owners)))


def neutral_spread(free: int, territories: int, homes: int) -> tuple[int]:
    """The one neutral territory size that splits ``free`` places into the territories the
    homes leave of ``territories``, at least one."""
    return (max(1, math.ceil(free / max(1, territories - homes))),)


def _pieces(places: Sequence[int], nbr: Mapping[int, set[int]]) -> list[list[int]]:
    left = set(places)
    out: list[list[int]] = []
    for start in sorted(places):
        if start not in left:
            continue
        left.discard(start)
        piece, stack = [start], [start]
        while stack:
            for n in sorted(nbr.get(stack.pop(), ())):
                if n in left:
                    left.discard(n)
                    piece.append(n)
                    stack.append(n)
        out.append(sorted(piece))
    return out


def settle(
    territory: Sequence[int], owners: Sequence[int | None], realised: Iterable[Pair]
) -> tuple[tuple[int, ...], tuple[int | None, ...]]:
    """The territory of each place once the places have grown, and the owner of each
    territory. A territory splits into its pieces connected over ``realised``, and only the
    piece holding a home keeps an owner. Territories come out numbered by their lowest
    place."""
    groups: dict[int, list[int]] = collections.defaultdict(list)
    for p, t in enumerate(territory):
        groups[t].append(p)
    nbr = _neighbours(realised)
    pieces = sorted(piece for t in sorted(groups) for piece in _pieces(groups[t], nbr))
    settled = [0] * len(territory)
    lords: list[int | None] = []
    for t, piece in enumerate(pieces):
        for p in piece:
            settled[p] = t
        homes = [owners[p] for p in piece if owners[p] is not None]
        lords.append(homes[0] if homes else None)
    return tuple(settled), tuple(lords)


def _pool(counts: Sequence[TerritoryCount], players: int) -> list[TerritoryCount]:
    full = collections.Counter(c.players for c in counts)
    near = [p for p, n in full.items() if n >= NEAREST_RECORDS]
    if not near:
        return list(counts)
    best = min(near, key=lambda p: (abs(p - players), p))
    return [c for c in counts if c.players == best]


def draw_territory_count(
    counts: Sequence[TerritoryCount], players: int, land: int, rng: random.Random
) -> int:
    """A territory count from one corpus record. The records whose land
    lies within ``LAND_BAND`` times ``land`` keep the nearest player count that has
    ``NEAREST_RECORDS`` maps, or the whole corpus does when no player count in the band has
    as many. The record is drawn among the ``NEAREST_RECORDS`` of them whose land is
    closest. Without records the count is one territory more than ``players``."""
    if not counts or land <= 0:
        return players + 1
    band = [c for c in counts if abs(math.log(c.land / land)) <= math.log(LAND_BAND)]
    pool = _pool(band, players) if band else []
    if len(pool) < NEAREST_RECORDS:
        pool = _pool(counts, players)
    pool.sort(key=lambda c: (abs(math.log(c.land / land)), c.territories, c.land))
    return rng.choice(pool[:NEAREST_RECORDS]).territories


def _fronts(territory: Sequence[int], realised: Iterable[Pair]) -> dict[Pair, list[Pair]]:
    fronts: dict[Pair, list[Pair]] = collections.defaultdict(list)
    for a, b in sorted(realised):
        ta, tb = territory[a], territory[b]
        if ta != tb:
            fronts[(min(ta, tb), max(ta, tb))].append((a, b))
    return fronts


def detour_doors(
    choices: Mapping[Pair, Sequence[Pair]],
    joined: Iterable[Pair],
    max_hop: int,
    rng: random.Random,
) -> dict[Pair, int]:
    """The doors to add on the touching territory pairs, keys of ``choices``, that more than
    ``max_hop`` of the ``joined`` territory pairs part or none joins. The walk goes in sorted
    order, each door counts for the pairs after it, and each stands on a zone pair drawn
    from the pair's ``choices``."""
    graph = set(joined)
    count = max((t for tp in (*choices, *graph) for t in tp), default=-1) + 1
    out: dict[Pair, int] = {}
    for (ta, tb), pairs in sorted(choices.items()):
        hop = hop_counts(count, graph, ta)[tb]
        if hop is not None and hop <= max_hop:
            continue
        out[rng.choice(pairs)] = 1
        graph.add((ta, tb))
    return out


def draw_doors(
    territory: Sequence[int],
    borders: tuple[Iterable[Pair], Collection[Pair]],
    pair_doors: Sequence[int],
    rng: random.Random,
    links: Collection[Pair] = (),
) -> dict[Pair, int]:
    """The door count of each zone pair that holds a door, from ``borders``, the realised
    zone pairs and the planned ones. A spanning forest over the bordering territory pairs,
    those a planned zone pair joins first, puts one door on each of its pairs, on one of
    their planned zone pairs when they have some. ``detour_doors`` then joins every touching
    pair more than ``MAX_HOP`` hops apart over the forest and ``links``, on the same choice
    of zone pairs. For each joined territory pair, a count drawn from ``pair_doors`` above
    one adds a second door on another zone pair of the same territory pair, or on the same
    zone pair when it is the only one."""
    realised, planned = borders
    fronts = _fronts(territory, realised)
    choices = {tp: [e for e in pairs if e in planned] or pairs for tp, pairs in fronts.items()}
    first = {tp for tp, pairs in fronts.items() if any(e in planned for e in pairs)}
    forest = sorted(spanning_forest(fronts, first, lambda _e: 1.0, rng))
    doors = {rng.choice(choices[tp]): 1 for tp in forest}
    doors |= detour_doors(choices, {*forest, *links}, MAX_HOP, rng)
    for door in sorted(doors):
        if min(MAX_DOORS, draw_count(pair_doors, rng)) < 2:
            continue
        a, b = territory[door[0]], territory[door[1]]
        others = [e for e in fronts[(min(a, b), max(a, b))] if e != door]
        if others:
            doors[rng.choice(others)] = 1
        else:
            doors[door] = 2
    return doors


def wall_width(hops: int | None, side: int) -> int:
    """The tiles a wall takes between two territories ``hops`` doors apart, None when no
    door path joins them, on a map ``side`` tiles wide: thin one door apart, wider two
    apart, widest three or more apart or cut off."""
    least, per = WALL_WIDTHS[min(hops, len(WALL_WIDTHS)) - 1 if hops else -1]
    return max(least, side // per)


def wall_depths(
    territory: Sequence[int], doors: Collection[Pair], side: int, links: Collection[Pair] = ()
) -> dict[Pair, int]:
    """The wall width between every zone pair ``(a, b)``, ``a < b``, of two territories,
    from the hops between their territories over the doors and ``links`` on a map ``side``
    tiles wide. A pair left out walls one tile wide."""
    own = max(territory, default=-1) + 1
    joined = {(territory[a], territory[b]) for a, b in doors} | set(links)
    count = max([own, *(t + 1 for tp in joined for t in tp)])
    hops = [hop_counts(count, joined, t) for t in range(own)]
    out: dict[Pair, int] = {}
    for b, tb in enumerate(territory):
        for a in range(b):
            ta = territory[a]
            if ta != tb and (width := wall_width(hops[ta][tb], side)) > 1:
                out[(a, b)] = width
    return out


def wall_kinds(
    territory: Sequence[int],
    realised: Iterable[Pair],
    inner: Mapping[Pair, AdjacencyKind],
    doors: Collection[Pair],
) -> dict[Pair, AdjacencyKind]:
    """The kind of every realised pair: its kind in ``inner`` inside a territory, gated
    where it holds a door, and closed on every other border between two territories."""
    return {
        (a, b): inner[(a, b)]
        if territory[a] == territory[b]
        else AdjacencyKind.GATED
        if (a, b) in doors
        else AdjacencyKind.CLOSED
        for a, b in sorted(realised)
    }


def _crossings(entrances: Sequence[Entrance], other: int) -> list[Entrance]:
    return [e for e in entrances if e.other == other]


def territory_plan(
    territory: Sequence[int],
    owners: Sequence[int | None],
    doors: Collection[Pair],
    passages: Passages,
) -> TerritoryPlan:
    """The published partition: the territory of each zone, the owner of each territory,
    and one door per crossing the passage plan gave a door pair."""
    planned: list[PlannedDoor] = []
    for a, b in sorted(doors):
        ta, tb = territory[a], territory[b]
        side_a = _crossings(passages.entrances.get(a, ()), b)
        side_b = _crossings(passages.entrances.get(b, ()), a)
        planned += [
            PlannedDoor((a, b), (ta, tb), (owners[ta], owners[tb]), (ea.rep, eb.rep))
            for ea, eb in zip(side_a, side_b, strict=True)
        ]
    return TerritoryPlan(dict(enumerate(territory)), tuple(owners), tuple(planned))


def _doorless(plan: TerritoryPlan, realised: Iterable[Pair], walled: bool) -> list[int]:
    if len(plan.owners) < 2:
        return []
    opened = {t for d in plan.doors for t in d.territories}
    near: set[int] = set()
    for a, b in realised:
        ta, tb = plan.zones[a], plan.zones[b]
        if ta != tb:
            near |= {ta, tb}
    return [
        owner
        for t, owner in enumerate(plan.owners)
        if owner is not None and t not in opened and (t in near) == walled
    ]


def stranded(plan: TerritoryPlan, realised: Iterable[Pair]) -> list[int]:
    """The players whose territory borders another over ``realised`` yet holds no door."""
    return _doorless(plan, realised, walled=True)


def islanded(plan: TerritoryPlan, realised: Iterable[Pair]) -> list[int]:
    """The players whose territory holds no door because water parts it from every other
    territory: it borders none over ``realised``."""
    return _doorless(plan, realised, walled=False)


def unreached(plan: TerritoryPlan, realised: Iterable[Pair]) -> list[int]:
    """The territories no home reaches over the doors, among those on the land of a home:
    joined to it by borders over ``realised``."""
    count = len(plan.owners)
    homes = [t for t, owner in enumerate(plan.owners) if owner is not None]
    zone = plan.zones
    touching = {(zone[a], zone[b]) for a, b in realised if zone[a] != zone[b]}
    doors = {d.territories for d in plan.doors}

    def reach(edges: Iterable[Pair]) -> set[int]:
        hops = [hop_counts(count, edges, h) for h in homes]
        return {t for row in hops for t, hop in enumerate(row) if hop is not None}

    return sorted(reach(touching) - reach(doors))

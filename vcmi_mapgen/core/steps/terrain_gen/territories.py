"""The territories of a place map: each home with a corpus-drawn number of its neighbours,
the other places grouped into neutral territories sized from the corpus spread, and the
doors that join them. Every border between two territories without a door is walled."""

import collections
import random
from collections.abc import Collection, Iterable, Mapping, Sequence

from vcmi_mapgen.core.model import Entrance
from vcmi_mapgen.core.planning.entrances import Passages
from vcmi_mapgen.core.reading.borders import AdjacencyKind
from vcmi_mapgen.core.steps.terrain_gen.border_kinds import spanning_forest
from vcmi_mapgen.core.steps.terrain_gen.result import PlannedDoor, TerritoryPlan

type Pair = tuple[int, int]

MAX_DOORS = 2


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
    neutral_zones: Sequence[int],
    rng: random.Random,
) -> tuple[int, ...]:
    """The territory of each place, where ``owners[p]`` is the player place ``p`` is home
    to. Each home in place order takes itself and a random set of its neighbours over
    ``edges``, a count drawn from ``player_zones`` in all, clamped to the neighbours it
    has. The other places group into neutral territories sized from ``neutral_zones``."""
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
    for t, group in enumerate(group_neutral(rest, inner, neutral_zones, rng), len(homes)):
        for p in group:
            territory[p] = t
    return tuple(territory[p] for p in range(len(owners)))


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


def draw_doors(
    territory: Sequence[int],
    realised: Iterable[Pair],
    planned: Collection[Pair],
    pair_doors: Sequence[int],
    rng: random.Random,
) -> dict[Pair, int]:
    """The door count of each zone pair that holds a door. A spanning forest over the
    bordering territory pairs, those a planned zone pair joins first, puts one door on each
    of its pairs, on one of their planned zone pairs when they have some. A count drawn
    from ``pair_doors`` above one adds a second door on another zone pair of the same
    territory pair, or on the same zone pair when it is the only one."""
    fronts: dict[Pair, list[Pair]] = collections.defaultdict(list)
    for a, b in sorted(realised):
        ta, tb = territory[a], territory[b]
        if ta != tb:
            fronts[(min(ta, tb), max(ta, tb))].append((a, b))
    first = {tp for tp, pairs in fronts.items() if any(e in planned for e in pairs)}
    doors: dict[Pair, int] = {}
    for tp in sorted(spanning_forest(fronts, first, lambda _e: 1.0, rng)):
        pairs = fronts[tp]
        door = rng.choice([e for e in pairs if e in planned] or pairs)
        doors[door] = 1
        if min(MAX_DOORS, draw_count(pair_doors, rng)) < 2:
            continue
        others = [e for e in pairs if e != door]
        if others:
            doors[rng.choice(others)] = 1
        else:
            doors[door] = 2
    return doors


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

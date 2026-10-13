"""The corpus draws a places map starts from (map-math 4.1): how many places, the role mix
and target size their shapes grow to, and how much more often two roles border in the corpus
than at random."""

import collections
import math
import random
from collections.abc import Sequence

from vcmi_mapgen.core.priors.places import PlaceCount, PlaceStats
from vcmi_mapgen.core.reading.places import PlaceRole

MIN_PLACE_AREA = 60
"""Every place must be able to reach this many tiles, which caps the place count."""

SIZE_FLOOR = 30
"""No place is planned smaller than this."""

HOME_FLOOR = 150
"""No home is planned smaller than this, the area a player town needs."""

NEAREST_RECORDS = 5

type Edge = tuple[int, int]


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

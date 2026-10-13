"""The roles of the places once the shapes, the homes and the territories stand: a
Metropolis walk over the non-home places that rewards the role pairs the corpus borders
often and the sizes the corpus gives each role."""

import collections
import math
import random
from collections.abc import Collection, Sequence
from typing import cast

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.priors.places import PlaceStats
from vcmi_mapgen.core.reading.places import PlaceRole
from vcmi_mapgen.core.steps.terrain_gen.layout import Layout
from vcmi_mapgen.core.steps.terrain_gen.place_draws import pair_affinity
from vcmi_mapgen.core.steps.terrain_gen.place_map import label_adjacency

SWEEPS = 40
"""Proposals per non-home place in the walk."""


def size_scores(stats: PlaceStats, shares: Sequence[float]) -> dict[PlaceRole, list[float]]:
    """For each non-home role the corpus saw, the log of its share of the corpus places
    times the density of each share in ``shares`` under the role's corpus size fractions.
    The density is a Gaussian kernel estimate on the log share with Silverman's
    bandwidth."""
    out: dict[PlaceRole, list[float]] = {}
    seen = {r: stats.rel_size.get(r.value, ()) for r in PlaceRole if r != PlaceRole.HOME}
    total = sum(len(v) for v in seen.values())
    x = np.log(np.maximum(np.array(shares, dtype=np.float64), 1e-9))
    for role, samples in seen.items():
        if not samples:
            continue
        s = np.log(np.maximum(np.array(samples, dtype=np.float64), 1e-9))
        sd = float(np.std(s)) or 1.0
        h = 1.06 * sd * math.pow(len(samples), -0.2)
        z: NDArray[np.float64] = np.subtract.outer(x, s) / h
        bell: NDArray[np.float64] = np.exp(-0.5 * z * z)
        mean = cast("NDArray[np.float64]", np.mean(bell, axis=1))
        norm = h * math.sqrt(2 * math.pi)
        prior = math.log(len(samples) / total)
        dens = cast("list[float]", mean.tolist())
        out[role] = [prior + math.log(max(d / norm, 1e-12)) for d in dens]
    return out


def allowed_roles(roles: Collection[PlaceRole], degree: int, crossing: bool) -> list[PlaceRole]:
    """The roles a non-home place may take among ``roles``: a pocket only with one
    neighbour, a pass only when a neighbour lies in another territory. Middle stands in when
    nothing else is left."""
    out = [
        r
        for r in sorted(roles)
        if (r != PlaceRole.POCKET or degree == 1) and (r != PlaceRole.PASS or crossing)
    ]
    return out or [PlaceRole.MIDDLE]


def label_roles(
    layout: Layout,
    homes: Collection[int],
    territory: Sequence[int],
    stats: PlaceStats,
    rng: random.Random,
) -> list[PlaceRole]:
    """The role of every place of ``layout``: home for each of ``homes``, and for the rest
    the end of a Metropolis walk over the realised adjacency. The energy is minus the
    corpus role-pair affinity of every border, minus each place's log size score. Each
    place starts on its best size score and keeps to ``allowed_roles``."""
    n = layout.places
    area = collections.Counter(z for row in layout.label for z in row if z >= 0)
    land = sum(area.values()) or 1
    scores = size_scores(stats, [area[p] / land for p in range(n)])
    nbr: list[set[int]] = [set() for _ in range(n)]
    for a, b in label_adjacency(layout.label):
        nbr[a].add(b)
        nbr[b].add(a)
    free = [p for p in range(n) if p not in homes]
    allowed = {
        p: allowed_roles(scores, len(nbr[p]), any(territory[q] != territory[p] for q in nbr[p]))
        for p in free
    }

    def unary(p: int, r: PlaceRole) -> float:
        return -scores[r][p] if r in scores else 0.0

    roles = [PlaceRole.HOME if p in homes else PlaceRole.MIDDLE for p in range(n)]
    for p in free:
        roles[p] = min(allowed[p], key=lambda r: (unary(p, r), r))
    affinity = pair_affinity(stats)
    for _ in range(SWEEPS * len(free)):
        p = rng.choice(free)
        new = rng.choice(allowed[p])
        old = roles[p]
        if new == old:
            continue
        delta = unary(p, new) - unary(p, old)
        delta -= sum(affinity[new, roles[q]] - affinity[old, roles[q]] for q in nbr[p])
        if delta <= 0 or rng.random() < math.exp(-delta):
            roles[p] = new
    return roles

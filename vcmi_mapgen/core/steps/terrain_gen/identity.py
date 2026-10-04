"""Each place's dominant terrain (map-math 4.3): one terrain per palette region, drawn by
Metropolis from the corpus terrain of its places' roles and the corpus preference for which
terrain blobs border which. Bordering regions differ."""

import math
import random
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.priors.macro import MacroStats
from vcmi_mapgen.core.priors.places import PlaceStats
from vcmi_mapgen.core.reading.places import PlaceRole
from vcmi_mapgen.core.steps.terrain_gen.macro import pair_probs
from vcmi_mapgen.core.steps.terrain_gen.palette import neighbours
from vcmi_mapgen.core.steps.terrain_gen.place_graph import Edge

SWEEPS = 60
CLASH = 1e6


def town_terrains(catalog: Catalog) -> frozenset[Terrain]:
    """The land terrains the random town may stand on."""
    kind = catalog.random_town().kind
    return frozenset(t for t in Terrain if t.is_land and catalog.allowed_on(kind, t))


def role_costs(
    stats: PlaceStats, roles: Collection[PlaceRole], domain: Sequence[Terrain]
) -> dict[PlaceRole, dict[Terrain, float]]:
    """Minus the log share of each terrain among the corpus dominants of each role."""
    out: dict[PlaceRole, dict[Terrain, float]] = {}
    for role in roles:
        seen = stats.dominant.get(role.value, {})
        total = sum(seen.get(t.value, 0) for t in domain) + 0.5 * len(domain)
        out[role] = {t: -math.log((seen.get(t.value, 0) + 0.5) / total) for t in domain}
    return out


def _domains(
    roles: Sequence[PlaceRole],
    groups: Sequence[int],
    domain: Sequence[Terrain],
    town: Collection[Terrain],
) -> list[list[Terrain]]:
    homes = [t for t in domain if t in town] or list(domain)
    held = {g for r, g in zip(roles, groups, strict=True) if r == PlaceRole.HOME}
    return [homes if g in held else list(domain) for g in range(max(groups, default=-1) + 1)]


@dataclass(frozen=True, slots=True)
class Palette:
    """Each place's role, the realised place adjacency and each place's palette region."""

    roles: Sequence[PlaceRole]
    adjacency: Collection[Edge]
    groups: Sequence[int]


def assign_dominants(
    palette: Palette,
    stats: tuple[PlaceStats, MacroStats],
    town: Collection[Terrain],
    rng: random.Random,
) -> list[Terrain]:
    """One terrain per palette region among the corpus surface terrains, a region holding a
    home among the ones a town may stand on, returned per place. Energy is the role cost of
    every member place plus minus the log corpus probability of every bordering region
    pair. Two bordering regions never share a terrain."""
    places, macro = stats
    roles, adjacency, groups = palette.roles, palette.adjacency, palette.groups
    domain = sorted(Terrain(t) for t in macro.terr_share)
    allowed = _domains(roles, groups, domain, town)
    cost = role_costs(places, set(roles), domain)
    pair: Mapping[tuple[int, int], float] = {
        k: -math.log(p) for k, p in pair_probs(macro, [t.value for t in domain]).items()
    }
    members: list[list[PlaceRole]] = [[] for _ in allowed]
    for r, g in zip(roles, groups, strict=True):
        members[g].append(r)
    own = [{t: sum(cost[r][t] for r in m) for t in domain} for m in members]
    nbr = neighbours(
        len(allowed), {(groups[a], groups[b]) for a, b in adjacency if groups[a] != groups[b]}
    )
    terr: list[Terrain] = []
    for k, ok in enumerate(allowed):
        taken = {terr[j] for j in nbr[k] if j < k}
        free = [t for t in ok if t not in taken] or ok
        terr.append(min(free, key=lambda t: (own[k][t], t)))

    def local(k: int, t: Terrain) -> float:
        return own[k][t] + sum(
            CLASH if t == terr[j] else pair[t.value, terr[j].value] for j in nbr[k]
        )

    for _ in range(SWEEPS * len(allowed)):
        k = rng.randrange(len(allowed))
        t = rng.choice(allowed[k])
        d_e = local(k, t) - local(k, terr[k])
        if d_e <= 0 or rng.random() < math.exp(-d_e):
            terr[k] = t
    return [terr[g] for g in groups]

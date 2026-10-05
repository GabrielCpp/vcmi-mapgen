"""How many gameplay objects the whole map holds: per purpose at the corpus rate per tile,
times a density multiplier, then per family by the corpus count of each family the map can
offer."""

from __future__ import annotations

import random
from collections.abc import Iterable, Mapping, Sequence

from vcmi_mapgen.core.model.purpose import FLANKED, VISIT_PURPOSES, Purpose
from vcmi_mapgen.core.placement.intensity import density, stoch_round
from vcmi_mapgen.core.priors.gameplay import TerrainStats
from vcmi_mapgen.core.reading.families import TOP_LEVEL, dwelling_family, mine_family

RANKS: tuple[str, ...] = (
    Purpose.TOWN,
    Purpose.MINE,
    Purpose.DWELLING,
    Purpose.BANK,
    *VISIT_PURPOSES,
)


def purpose_quota(
    grounds: Iterable[tuple[int, TerrainStats]], mult: float, towns: int, rng: random.Random
) -> dict[str, int]:
    """Per purpose, the objects ``grounds`` hold at the corpus rate of their terrain times
    ``mult``. The ``towns`` already standing count inside the town quota."""
    expected = dict.fromkeys(RANKS, 0.0)
    for area, st in grounds:
        dens = density(st)
        for p in FLANKED:
            expected[p] += area * dens.get(p, 0.0) * mult
    out = {p: stoch_round(rng, expected[p]) for p in RANKS}
    out[Purpose.TOWN] = max(0, out[Purpose.TOWN] - towns)
    return out


def split(n: int, weights: Mapping[str, float]) -> dict[str, int]:
    """``n`` split over the keys of ``weights`` by largest remainder, the earlier key first
    on a tie. Equal weights stand in when every weight is zero."""
    keys = list(weights)
    if not keys:
        return {}
    total = sum(weights.values())
    shares = [weights[k] / total if total > 0 else 1 / len(keys) for k in keys]
    quotas = [n * s for s in shares]
    out = [int(q) for q in quotas]
    order = sorted(range(len(keys)), key=lambda i: (-(quotas[i] - out[i]), i))
    for i in order[: n - sum(out)]:
        out[i] += 1
    return dict(zip(keys, out, strict=True))


def purpose_families(purpose: str, resources: Sequence[str]) -> list[str]:
    """The families of ``purpose`` a map offers: one per mine resource in ``resources``, one
    per dwelling level 0..7, the purpose itself otherwise."""
    if purpose == Purpose.MINE:
        return [mine_family(r) for r in sorted(resources)]
    if purpose == Purpose.DWELLING:
        return [dwelling_family(n) for n in range(TOP_LEVEL + 1)]
    return [purpose]


def family_quota(
    purposes: Mapping[str, int],
    resources: Sequence[str],
    corpus: Mapping[str, Sequence[int]],
) -> dict[str, int]:
    """Per family, its share of its purpose's quota by the corpus count of each family."""
    out: dict[str, int] = {}
    for purpose, n in purposes.items():
        fams = purpose_families(purpose, resources)
        out.update(split(n, {f: float(sum(corpus.get(f, ()))) for f in fams}))
    return out

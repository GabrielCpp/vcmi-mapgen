"""How many gameplay objects the whole map holds: one count per group of families, each by
the rule the group rules choose, times a density multiplier, then per family by the corpus
count of each family the map can offer.

The resource mines follow the corpus curve over the map's land area and player count. The
weekly producers follow the mine rate per tile times their corpus share of the mines. Every
other purpose follows its own corpus rate per tile."""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from vcmi_mapgen.core.model.purpose import VISIT_PURPOSES, Purpose
from vcmi_mapgen.core.placement.intensity import density, stoch_round
from vcmi_mapgen.core.priors.gameplay import TerrainStats
from vcmi_mapgen.core.priors.mines import MineCurve
from vcmi_mapgen.core.reading.families import TOP_LEVEL, dwelling_family, mine_family
from vcmi_mapgen.core.reading.mines import RESOURCE_MINES, MapMeasure
from vcmi_mapgen.core.reading.supply import SUPPLY

RANKS: tuple[str, ...] = (
    Purpose.TOWN,
    Purpose.MINE,
    Purpose.DWELLING,
    Purpose.BANK,
    *VISIT_PURPOSES,
)

Grounds = Sequence[tuple[int, TerrainStats]]
Corpus = Mapping[str, Sequence[int]]


class CountRule(Protocol):
    def expected(self) -> float:
        """The objects a group should hold on the map, before the density multiplier."""
        ...


@dataclass(frozen=True, slots=True)
class RateRule:
    """Each terrain's area times its corpus rate per tile of ``purpose``, times ``share``."""

    grounds: Grounds
    purpose: str
    share: float = 1.0

    def expected(self) -> float:
        rate = sum(area * density(st).get(self.purpose, 0.0) for area, st in self.grounds)
        return rate * self.share


@dataclass(frozen=True, slots=True)
class CurveRule:
    """The resource mine curve at the map's measure."""

    curve: MineCurve
    measure: MapMeasure

    def expected(self) -> float:
        return self.curve.expected(self.measure.land, self.measure.players)


@dataclass(frozen=True, slots=True)
class Group:
    """Families counted by one rule, less ``per_town`` objects for each town on the map."""

    families: tuple[str, ...]
    rule: CountRule
    per_town: int = 0


@dataclass(frozen=True, slots=True)
class MapCount:
    """What the group rules read of a map: its terrain areas with their corpus statistics,
    its measure, the mine resources it offers, and the corpus count of each family."""

    grounds: Grounds
    measure: MapMeasure
    resources: Sequence[str]
    corpus: Corpus

    def weight(self, families: Sequence[str]) -> float:
        return float(sum(sum(self.corpus.get(f, ())) for f in families))


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


def purpose_families(purpose: str) -> tuple[str, ...]:
    """The families of a purpose other than the mines: one per dwelling level 0..7, the
    purpose itself otherwise."""
    if purpose == Purpose.DWELLING:
        return tuple(dwelling_family(n) for n in range(TOP_LEVEL + 1))
    return (purpose,)


def group_rules(curve: MineCurve, count: MapCount) -> list[Group]:
    """Every group in drawing order, each with the rule that counts it."""
    offered = [mine_family(r) for r in sorted(count.resources)]
    supplied = {mine_family(r) for r in SUPPLY}
    mines_of = {mine_family(r) for r in RESOURCE_MINES}
    resource = tuple(f for f in offered if f in mines_of and f not in supplied)
    producers = tuple(f for f in offered if f not in mines_of)
    mines = count.weight(offered)
    share = count.weight(producers) / mines if mines > 0 else 0.0
    others = [p for p in RANKS if p not in (Purpose.TOWN, Purpose.MINE)]
    return [
        Group((Purpose.TOWN,), RateRule(count.grounds, Purpose.TOWN)),
        Group(resource, CurveRule(curve, count.measure), len(SUPPLY)),
        Group(producers, RateRule(count.grounds, Purpose.MINE, share)),
        *(Group(purpose_families(p), RateRule(count.grounds, p)) for p in others),
    ]


def family_quota(
    groups: Sequence[Group], corpus: Corpus, mult: float, towns: int, rng: random.Random
) -> dict[str, int]:
    """Per family, its share of its group's count by the corpus count of each family. Each
    group draws one rounding of its expectation times ``mult``, in order. The ``towns``
    already standing count inside the town quota and take their group's ``per_town`` off
    each later group."""
    out: dict[str, int] = {}
    for group in groups:
        n = stoch_round(rng, group.rule.expected() * mult)
        if group.families == (Purpose.TOWN,):
            n = max(0, n - towns)
        n = max(0, n - group.per_town * towns)
        out.update(split(n, {f: float(sum(corpus.get(f, ()))) for f in group.families}))
    return out


def paired(groups: Sequence[Group]) -> frozenset[str]:
    """The families each new town's own objects count against."""
    return frozenset(f for g in groups if g.per_town for f in g.families)

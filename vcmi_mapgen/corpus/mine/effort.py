"""Mine the effort band edges from the effort at every corpus artifact pickup."""

import itertools
import math
import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState, PlacedObject
from vcmi_mapgen.core.model.artifact import TIERS, ArtifactTier
from vcmi_mapgen.core.priors.effort import BANDS, EffortPriors
from vcmi_mapgen.core.reading.effort import effort_map
from vcmi_mapgen.core.reading.routes import Spot, route_map

type TownKey = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class ArtifactTiers:
    """The artifact class of each random artifact kind and of each named artifact."""

    kinds: Mapping[str, ArtifactTier]
    names: Mapping[str, ArtifactTier]

    @staticmethod
    def of(catalog: Catalog) -> "ArtifactTiers":
        return ArtifactTiers(
            kinds={catalog.random_artifact(t).kind.lower(): t for t in TIERS},
            names={a: t for t in TIERS for a in catalog.artifacts(t)},
        )

    def tier(self, catalog: Catalog, obj: PlacedObject) -> ArtifactTier | None:
        kind = obj.kind.lower()
        if kind in self.kinds:
            return self.kinds[kind]
        subtype = catalog.identity_of(obj.kind).subtype
        return self.names.get(subtype) if subtype is not None else None


def _interactive(obj: PlacedObject) -> list[Spot]:
    cells = [t for t, role in obj.footprint.at(obj.x, obj.y) if role.interactive]
    return [Spot(obj.level, x, y) for x, y in cells or [(obj.x, obj.y)]]


def pickup_efforts(
    catalog: Catalog,
    state: MapState,
    owners: Mapping[TownKey, int],
    tiers: ArtifactTiers,
    toll: Sequence[int],
) -> list[tuple[ArtifactTier, int]]:
    """The effort in days at each artifact pickup a home reaches on one map, with its class.
    The homes are the entrances of the towns a player owns."""
    homes = [s for o in state.objs if (o.x, o.y, o.level) in owners for s in _interactive(o)]
    if not homes:
        return []
    em = effort_map(route_map(catalog, state), homes, toll)
    out: list[tuple[ArtifactTier, int]] = []
    for o in state.objs:
        tier = tiers.tier(catalog, o)
        if tier is None:
            continue
        efforts = [e for s in _interactive(o) if (e := em.at(s)) is not None]
        if efforts:
            out.append((tier, min(e.total for e in efforts)))
    return out


def _quantiles(values: Sequence[int]) -> tuple[int, ...]:
    cuts = statistics.quantiles(values, n=BANDS, method="inclusive")
    return tuple(round(c) for c in cuts)


def band_edges(medians: Sequence[float], values: Sequence[int]) -> tuple[int, ...]:
    """The edges at the geometric midpoints of consecutive class medians, or the effort
    quartiles when the medians do not rise."""
    edges = tuple(
        round(math.sqrt(max(a, 1.0) * max(b, 1.0))) for a, b in itertools.pairwise(medians)
    )
    if all(a < b for a, b in itertools.pairwise(edges)):
        return edges
    return _quantiles(values)


def mine_effort(
    catalog: Catalog,
    maps: Iterable[MapState],
    owners: Iterable[Mapping[TownKey, int]],
    tuned: EffortPriors,
) -> EffortPriors:
    """The ``tuned`` priors with their band edges read from the effort at every corpus
    artifact pickup of each class. The toll and the baskets stay as tuned."""
    tiers = ArtifactTiers.of(catalog)
    by_tier: dict[ArtifactTier, list[int]] = {t: [] for t in TIERS}
    for state, own in zip(maps, owners, strict=True):
        for tier, total in pickup_efforts(catalog, state, own, tiers, tuned.toll):
            by_tier[tier].append(total)
    medians = {t: float(statistics.median(v)) for t, v in by_tier.items() if v}
    values = sorted(v for vs in by_tier.values() for v in vs)
    edges = band_edges([medians[t] for t in TIERS if t in medians], values)
    return replace(
        tuned,
        edges=edges,
        medians=medians,
        counts={t: len(v) for t, v in by_tier.items()},
    )

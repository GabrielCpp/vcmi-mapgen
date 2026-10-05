"""The set dealer: how many sets a map carries, which complete sets fit the held slots, and
which slot takes which part."""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model.artifact import TIERS, ArtifactSet, ArtifactTier
from vcmi_mapgen.core.priors.effort import BANDS
from vcmi_mapgen.core.steps.sets.slots import NO_HOME, Slot

QUOTA_AREA = 72 * 72
TOP_BANDS = 2


def set_quota(levels: int, size: int) -> int:
    """One set per 72x72 tiles over every level, at least one."""
    return max(1, round(levels * size * size / QUOTA_AREA))


def dealable(catalog: Catalog, water: bool) -> list[ArtifactSet]:
    """The sets whose every part the catalog places, without the water sets on a dry map."""
    return [
        s
        for s in catalog.artifact_sets()
        if (water or not s.water) and all(catalog.artifact(p) is not None for p in s.parts)
    ]


def tiers_of(catalog: Catalog) -> dict[str, ArtifactTier]:
    return {name: tier for tier in TIERS for name in catalog.artifacts(tier)}


def top_slots(slots: Sequence[Slot]) -> list[Slot]:
    """The slots a home reaches in the top two bands."""
    return [s for s in slots if s.home != NO_HOME and s.band > BANDS - TOP_BANDS]


def share(slots: Sequence[Slot], n: int) -> list[Slot] | None:
    """``n`` slots dealt round-robin over the homes, each home taking its costliest slot
    left. None when fewer than ``n`` slots remain."""
    if len(slots) < n:
        return None
    by_home: dict[int, list[Slot]] = {}
    for s in sorted(slots, key=lambda s: (-s.effort, s.held.level, s.held.tile)):
        by_home.setdefault(s.home, []).append(s)
    queues = [by_home[h] for h in sorted(by_home)]
    picks: list[Slot] = []
    while len(picks) < n:
        for q in queues:
            if q and len(picks) < n:
                picks.append(q.pop(0))
    return picks


@dataclass(frozen=True, slots=True)
class Deal:
    """One set and the slot each of its parts goes to."""

    name: str
    parts: tuple[tuple[Slot, str], ...]


def deal_one(picked: ArtifactSet, picks: Sequence[Slot], tiers: Mapping[str, ArtifactTier]) -> Deal:
    """The set's parts by tier, the best first, onto the picks by effort, the costliest
    first."""
    rank = {t: i for i, t in enumerate(TIERS)}
    parts = sorted(picked.parts, key=lambda p: -rank.get(tiers.get(p, TIERS[0]), 0))
    order = sorted(picks, key=lambda s: (-s.effort, s.held.level, s.held.tile))
    return Deal(picked.name, tuple(zip(order, parts, strict=True)))


@dataclass(frozen=True, slots=True)
class Dealer:
    """The sets the catalog places, each part's tier and the map's set quota."""

    sets: Sequence[ArtifactSet]
    tiers: Mapping[str, ArtifactTier]
    quota: int


def deal_sets(dealer: Dealer, slots: Sequence[Slot], rng: random.Random) -> list[Deal]:
    """Up to the quota of distinct sets, each drawn among those whose parts fit the top-band
    slots still free."""
    free = top_slots(slots)
    pool = sorted(dealer.sets, key=lambda s: s.name)
    deals: list[Deal] = []
    while len(deals) < dealer.quota:
        fits = [s for s in pool if len(s.parts) <= len(free)]
        if not fits:
            break
        picked = rng.choice(fits)
        pool.remove(picked)
        picks = share(free, len(picked.parts)) or []
        deals.append(deal_one(picked, picks, dealer.tiers))
        free = [s for s in free if s not in picks]
    return deals

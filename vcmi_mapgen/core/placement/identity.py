"""Identity picks: the editor's random classes, and one fixed identity drawn from a
candidate pool by a weight such as the corpus mix."""

import random
from collections.abc import Callable, Iterable

from vcmi_mapgen.core.catalog import ArtifactTier, Catalog
from vcmi_mapgen.core.model import Identity
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.priors.gameplay import TerrainStats

_ART_TIER_W: tuple[tuple[ArtifactTier | None, int], ...] = (
    ("treasure", 50),
    ("minor", 30),
    ("major", 15),
    (None, 5),
)


def pick_random_identity(
    catalog: Catalog, purpose: str, rng: random.Random, art_share: float = 0.45
) -> Identity | None:
    """Identity for a pickup. The H3 convention (user-mandated): favour the editor's RANDOM
    classes — random resource, tiered random artifacts — over fixed ones. `art_share` is
    the random-artifact probability for REWARD_PICKUP: high for guarded caches, low for
    unguarded scatter (which draws the fixed LOOT pool — treasure chests, campfires —
    weighted by the corpus mix, where the chest dominates). None means the caller draws a
    fixed identity instead."""
    if purpose == Purpose.RESOURCE_PILE and rng.random() < 0.6:
        return catalog.random_resource()
    if purpose == Purpose.REWARD_PICKUP and rng.random() < art_share:
        tiers: list[ArtifactTier | None] = [t for t, _w in _ART_TIER_W]
        tier = rng.choices(tiers, weights=[w for _t, w in _ART_TIER_W], k=1)[0]
        return catalog.random_artifact(tier)
    return None


def pick_kind(
    pool: Iterable[Identity], weight: Callable[[Identity], float], rng: random.Random
) -> Identity | None:
    """One fixed identity from `pool`, drawn by `weight` over its non-random members in
    animation order."""
    cands = sorted(
        (i for i in pool if "random" not in (i.type or "").lower()),
        key=lambda i: i.kind,
    )
    if not cands:
        return None
    return rng.choices(cands, weights=[weight(i) for i in cands], k=1)[0]


def pick_fixed_identity(
    pool: Iterable[Identity], purpose: str, st_t: TerrainStats, rng: random.Random
) -> Identity | None:
    w = st_t.anim_w.get(purpose, {})
    return pick_kind(pool, lambda i: w.get(i.kind.lower(), 0) + 0.2, rng)

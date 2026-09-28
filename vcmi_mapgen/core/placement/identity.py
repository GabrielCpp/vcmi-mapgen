"""Identity picks for a pickup: the editor's random classes first, then a fixed identity
weighted by the corpus mix."""

import random
from collections.abc import Iterable

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Identity
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.priors.gameplay import TerrainStats

RND_RES = "avtrndm0"  # randomResource


RND_ART = (
    ("avarnd1", 50, 3),
    ("avarnd2", 30, 5),  # (anim, pick weight, reward value):
    ("avarnd3", 15, 8),
    ("avarand", 5, 5),
)  # treasure/minor/major/any artifact


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
        return catalog.identity_of(RND_RES)
    if purpose == Purpose.REWARD_PICKUP and rng.random() < art_share:
        anim = rng.choices([a for a, _w, _v in RND_ART], weights=[w for _a, w, _v in RND_ART], k=1)[
            0
        ]
        return catalog.identity_of(anim)
    return None


def pick_fixed_identity(
    pool: Iterable[Identity], purpose: str, st_t: TerrainStats, rng: random.Random
) -> Identity | None:
    pool = sorted(
        (i for i in pool if "random" not in (i.type or "").lower()),
        key=lambda i: i.animation,
    )
    if not pool:
        return None
    w = st_t.anim_w.get(purpose, {})
    return rng.choices(pool, weights=[w.get(i.animation.lower(), 0) + 0.2 for i in pool], k=1)[0]

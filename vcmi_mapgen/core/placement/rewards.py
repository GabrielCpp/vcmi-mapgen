"""The reward payloads: the pandoraBox an unguarded pickup carries and the seer hut's
quest and payout. One builder draws every reward from a tier and the catalog's creatures."""

import random
from collections.abc import Mapping, Sequence

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Quest, Reward
from vcmi_mapgen.core.priors.effort import RewardTier

type Creatures = Mapping[int, Sequence[str]]

PANDORA_TIER = RewardTier(
    (45, 30, 25),
    (500, 1000, 1500, 2000, 3000, 5000),
    (1000, 1500, 2500, 5000, 7500, 10000),
    (3, 10),
    (2, 3),
)
SEERHUT_TIER = RewardTier(
    (35, 40, 25),
    (3000, 5000, 7500, 10000, 15000),
    (2500, 5000, 7500, 10000, 15000),
    (5, 20),
    (4, 5),
)

LEVELS = range(1, 8)


def creatures_of(catalog: Catalog) -> dict[int, list[str]]:
    """The catalog's creatures of each level 1..7."""
    return {lv: catalog.monsters(lv) for lv in LEVELS}


def draw_reward(rng: random.Random, tier: RewardTier, creatures: Creatures) -> Reward:
    """The one reward builder: gold, experience or a creature stack of one of the tier's
    levels, drawn from `creatures` by level. A stack whose level has no creature pays the
    tier's experience instead. The pandoraBox of open ground draws at `PANDORA_TIER`. The seer
    hut draws a tier up at `SEERHUT_TIER` (VCMI's own RMG seer-hut samples pay in the
    5-figure XP / dozens-of-creatures range: a seer hut costs the hero a whole side-quest,
    not a five-second detour)."""
    flavor = rng.choices(("gold", "experience", "stack"), weights=tier.weights, k=1)[0]
    if flavor == "gold":
        return Reward(gold=rng.choice(tier.gold))
    pool = creatures.get(rng.choice(tier.levels), ()) if flavor == "stack" else ()
    if not pool:
        return Reward(experience=rng.choice(tier.experience))
    return Reward(creatures=((rng.choice(pool), rng.randint(*tier.creatures)),))


def pandora_reward(rng: random.Random, creatures: Creatures) -> Reward:
    """The pandoraBox's reward, drawn at `PANDORA_TIER`. A pandoraBox without one is legal
    but permanently empty."""
    return draw_reward(rng, PANDORA_TIER, creatures)


def seerhut_quest(rng: random.Random, artifact: str, creatures: Creatures) -> Quest:
    """A seer hut's quest: the hero must carry `artifact`, and receives a reward drawn at
    `SEERHUT_TIER`."""
    return Quest(artifact, draw_reward(rng, SEERHUT_TIER, creatures))

"""The reward payloads: the pandoraBox an unguarded pickup carries and the seer hut's
quest and payout. One builder draws both rewards, a tier apart."""

import random
from dataclasses import dataclass

from vcmi_mapgen.core.model import Quest, Reward

PANDORA_CREATURES = (
    "pikeman",
    "centaur",
    "gremlin",
    "imp",
    "skeleton",
    "troglodyte",
    "goblin",
    "gnoll",
    "peasant",
)  # vanilla tier-1 dwelling
# creatures, one per RoE town plus the neutral peasant -- a modest
# unguarded-scatter payload, not cache-treasure tier.


@dataclass(frozen=True, slots=True)
class RewardTier:
    """The odds and amounts of one reward tier: flavour weights for gold, experience and
    creatures, the gold and experience amounts, and the creature stack range."""

    weights: tuple[int, int, int]
    gold: tuple[int, ...]
    experience: tuple[int, ...]
    creatures: tuple[int, int]


PANDORA_TIER = RewardTier(
    (45, 30, 25),
    (500, 1000, 1500, 2000, 3000, 5000),
    (1000, 1500, 2500, 5000, 7500, 10000),
    (3, 10),
)
SEERHUT_TIER = RewardTier(
    (35, 40, 25), (3000, 5000, 7500, 10000, 15000), (2500, 5000, 7500, 10000, 15000), (5, 20)
)


def draw_reward(rng: random.Random, tier: RewardTier) -> Reward:
    """The one reward builder: gold, experience or a tier-1 creature stack, drawn at
    `tier`. The pandoraBox draws at `PANDORA_TIER`, a modest unguarded-scatter payload. The
    seer hut draws a tier up at `SEERHUT_TIER` (VCMI's own RMG seer-hut samples pay in the
    5-figure XP / dozens-of-creatures range: a seer hut costs the hero a whole side-quest,
    not a five-second detour)."""
    flavor = rng.choices(("gold", "experience", "stack"), weights=tier.weights, k=1)[0]
    if flavor == "gold":
        return Reward(gold=rng.choice(tier.gold))
    if flavor == "experience":
        return Reward(experience=rng.choice(tier.experience))
    creature = rng.choice(PANDORA_CREATURES)
    return Reward(creatures=((creature, rng.randint(*tier.creatures)),))


def pandora_reward(rng: random.Random) -> Reward:
    """The pandoraBox's reward, drawn at `PANDORA_TIER`. A pandoraBox without one is legal
    but permanently empty."""
    return draw_reward(rng, PANDORA_TIER)


def seerhut_quest(rng: random.Random, artifact: str) -> Quest:
    """A seer hut's quest: the hero must carry `artifact`, and receives a reward drawn at
    `SEERHUT_TIER`."""
    return Quest(artifact, draw_reward(rng, SEERHUT_TIER))

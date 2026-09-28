"""The reward payloads: the pandoraBox an unguarded pickup carries and the seer hut's
quest and payout. One builder draws both rewards, a tier apart."""

import random
from dataclasses import dataclass

from vcmi_mapgen.core.model import JsonValue
from vcmi_mapgen.core.model.resource import Resource

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


RW_TEXT: dict[str, JsonValue] = {
    "exactStrings": None,
    "localStrings": None,
    "message": None,
    "numbers": None,
    "stringsTextID": None,
}


RW_LIMITER: dict[str, JsonValue] = {
    "allOf": [],
    "anyOf": [],
    "artifacts": [],
    "creatures": [],
    "dayOfWeek": 0,
    "daysPassed": 0,
    "heroExperience": 0,
    "heroLevel": -1,
    "manaPercentage": 0,
    "manaPoints": 0,
    "movePercentage": 0,
    "movePoints": 0,
    "noneOf": [],
    "primary": [0, 0, 0, 0],
    "secondary": [],
}


RW_REWARD: dict[str, JsonValue] = {
    "creatures": [],
    "creaturesChange": [],
    "heroExperience": 0,
    "heroLevel": 0,
    "manaDiff": 0,
    "manaOverflowFactor": 0,
    "manaPercentage": -1,
    "moveOverflowFactor": 0,
    "movePercentage": -1,
    "movePoints": 0,
    "primary": [0, 0, 0, 0],
    "resources": {},
    "secondary": [],
    "spellCast": {"level": 0},
}


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


def draw_reward(rng: random.Random, tier: RewardTier) -> dict[str, JsonValue]:
    """The one reward builder: gold, experience or a tier-1 creature stack, drawn at
    `tier`. The pandoraBox draws at `PANDORA_TIER`, a modest unguarded-scatter payload. The
    seer hut draws a tier up at `SEERHUT_TIER` (VCMI's own RMG seer-hut samples pay in the
    5-figure XP / dozens-of-creatures range: a seer hut costs the hero a whole side-quest,
    not a five-second detour)."""
    reward = dict(RW_REWARD)
    flavor = rng.choices(("gold", "experience", "creatures"), weights=tier.weights, k=1)[0]
    if flavor == "gold":
        reward["resources"] = {Resource.GOLD: rng.choice(tier.gold)}
    elif flavor == "experience":
        reward["heroExperience"] = rng.choice(tier.experience)
    else:
        reward["creatures"] = [
            {
                "type": f"core:{rng.choice(PANDORA_CREATURES)}",
                "amount": rng.randint(*tier.creatures),
            }
        ]
    return reward


def _rewardable(reward: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {
        "info": [
            {
                "limiter": dict(RW_LIMITER),
                "message": dict(RW_TEXT),
                "reward": reward,
                "visitType": 1,
            }
        ],
        "infoWindowType": 0,
        "onSelect": dict(RW_TEXT),
        "resetParameters": {"period": 0},
        "selectMode": "selectFirst",
        "visitMode": "unlimited",
    }


def pandora_reward(rng: random.Random) -> dict[str, JsonValue]:
    """A VCMI 'Rewardable' payload for a pandoraBox (schema captured verbatim from a real
    VCMI-RMG .vmap: `options.rewardable.info[].reward` alongside a sibling all-null
    `guardMessage`). Without this an unconfigured pandoraBox is legal but permanently
    empty -- every field defaults to 0/-1/null, which is a no-op reward."""
    return {
        "guardMessage": dict(RW_TEXT),
        "rewardable": _rewardable(draw_reward(rng, PANDORA_TIER)),
    }


def seerhut_quest(rng: random.Random, artifact_subtype: str) -> dict[str, JsonValue]:
    """VCMI 'Quest' + 'Rewardable' payload for a seerHut (schema captured verbatim from two
    real VCMI-RMG .vmap seerHut instances): a MISSION_ARTIFACT quest -- the hero must be
    CARRYING one specific named artifact -- gated via `quest.limiter.artifacts`. The sibling
    `rewardable.info[]` entry (paid out once the quest is satisfied) keeps the plain no-op
    base limiter: the artifact CHECK lives only in `quest.limiter`, confirmed against both
    reference instances, whose own `rewardable` limiter carries no `artifacts` restriction of
    its own."""
    quest_limiter: dict[str, JsonValue] = {
        **RW_LIMITER,
        "artifacts": [f"core:{artifact_subtype}"],
    }
    return {
        "quest": {
            "completedText": dict(RW_TEXT),
            "firstVisitText": dict(RW_TEXT),
            "limiter": quest_limiter,
            "nextVisitText": dict(RW_TEXT),
        },
        "rewardable": _rewardable(draw_reward(rng, SEERHUT_TIER)),
    }

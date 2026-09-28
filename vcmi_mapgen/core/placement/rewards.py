"""The pandoraBox reward payload an unguarded pickup carries."""

import random

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


def pandora_reward(rng: random.Random) -> dict[str, JsonValue]:
    """A VCMI 'Rewardable' payload for a pandoraBox (schema captured verbatim from a real
    VCMI-RMG .vmap: `options.rewardable.info[].reward` alongside a sibling all-null
    `guardMessage`). Without this an unconfigured pandoraBox is legal but permanently
    empty -- every field defaults to 0/-1/null, which is a no-op reward. Kept modest
    (gold/experience/a small creature stack): this fires from the unguarded-scatter loot
    pool, not a guarded cache."""
    reward = dict(RW_REWARD)
    flavor = rng.choices(("gold", "experience", "creatures"), weights=(45, 30, 25), k=1)[0]
    if flavor == "gold":
        reward["resources"] = {Resource.GOLD: rng.choice((500, 1000, 1500, 2000, 3000, 5000))}
    elif flavor == "experience":
        reward["heroExperience"] = rng.choice((1000, 1500, 2500, 5000, 7500, 10000))
    else:
        reward["creatures"] = [
            {"type": f"core:{rng.choice(PANDORA_CREATURES)}", "amount": rng.randint(3, 10)}
        ]
    return {
        "guardMessage": dict(RW_TEXT),
        "rewardable": {
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
        },
    }

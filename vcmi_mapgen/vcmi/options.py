"""Payloads to VCMI object options: the one place that knows the shape VCMI reads.

A pandoraBox and a seer hut pay through VCMI's `rewardable` block, captured verbatim from
real VCMI-RMG .vmap files. A seer hut's artifact check lives only in `quest.limiter`, and
its `rewardable` limiter stays the plain no-op base, as in both reference instances. A
guard without `character` is compliant and every creature joins free. A spellScroll has
the one subtype "object" and carries its spell in `options.spell`.

`CORE_SPELLS` is every base-game learnable spell (config/spells/{adventure,other,
offensive,timed}.json, indices 0-69). A town's mage guild picks from it, and VCMI reads an
absent list as "no spells available". Creature abilities (config/spells/ability.json) are
excluded, matching real VCMI RMG output."""

from __future__ import annotations

from vcmi_mapgen.core.model import (
    Dwelling,
    Guard,
    JsonValue,
    Payload,
    Quest,
    Reward,
    Scroll,
    Town,
)
from vcmi_mapgen.core.model.resource import Resource

CORE_SPELLS: list[JsonValue] = [
    "core:" + name
    for name in (
        "summonBoat",
        "scuttleBoat",
        "visions",
        "viewEarth",
        "disguise",
        "viewAir",
        "fly",
        "waterWalk",
        "dimensionDoor",
        "townPortal",
        "quicksand",
        "landMine",
        "forceField",
        "fireWall",
        "earthquake",
        "dispel",
        "cure",
        "resurrection",
        "animateDead",
        "sacrifice",
        "teleport",
        "removeObstacle",
        "clone",
        "fireElemental",
        "earthElemental",
        "waterElemental",
        "airElemental",
        "magicArrow",
        "iceBolt",
        "lightningBolt",
        "implosion",
        "chainLightning",
        "frostRing",
        "fireball",
        "inferno",
        "meteorShower",
        "deathRipple",
        "destroyUndead",
        "armageddon",
        "titanBolt",
        "shield",
        "airShield",
        "fireShield",
        "protectAir",
        "protectFire",
        "protectWater",
        "protectEarth",
        "antiMagic",
        "magicMirror",
        "bless",
        "curse",
        "bloodlust",
        "precision",
        "weakness",
        "stoneSkin",
        "disruptingRay",
        "prayer",
        "mirth",
        "sorrow",
        "fortune",
        "misfortune",
        "haste",
        "slow",
        "slayer",
        "frenzy",
        "counterstrike",
        "berserk",
        "hypnotize",
        "forgetfulness",
        "blind",
    )
]


TOWN_OPTIONS: dict[str, JsonValue] = {
    "buildings": {"allOf": ["core:fort", "core:tavern", "core:dwellingLvl1", "core:dwellingLvl2"]},
    "possibleSpells": CORE_SPELLS,
}


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


def _reward(reward: Reward) -> dict[str, JsonValue]:
    out = dict(RW_REWARD)
    if reward.gold:
        out["resources"] = {Resource.GOLD: reward.gold}
    if reward.experience:
        out["heroExperience"] = reward.experience
    if reward.creatures:
        out["creatures"] = [
            {"type": f"core:{creature}", "amount": amount} for creature, amount in reward.creatures
        ]
    return out


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


def _quest(quest: Quest) -> dict[str, JsonValue]:
    limiter: dict[str, JsonValue] = {**RW_LIMITER, "artifacts": [f"core:{quest.artifact}"]}
    return {
        "quest": {
            "completedText": dict(RW_TEXT),
            "firstVisitText": dict(RW_TEXT),
            "limiter": limiter,
            "nextVisitText": dict(RW_TEXT),
        },
        "rewardable": _rewardable(_reward(quest.reward)),
    }


def options_of(payload: Payload | None) -> dict[str, JsonValue] | None:
    """The VCMI `options` block for `payload`. A dwelling's `sameAsTown` holds the town's
    [x, y, level] until the export swaps in the town's instance name."""
    match payload:
        case Guard():
            return {"character": "hostile"}
        case Reward():
            return {"guardMessage": dict(RW_TEXT), "rewardable": _rewardable(_reward(payload))}
        case Quest():
            return _quest(payload)
        case Scroll(spell=spell):
            return {"spell": spell}
        case Town():
            return dict(TOWN_OPTIONS)
        case Dwelling(town=(x, y, level)):
            return {"sameAsTown": [x, y, level]}
        case None:
            return None

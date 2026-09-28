"""The purposes generation places objects for, and the groups the steps filter by."""

from enum import StrEnum


class Purpose(StrEnum):
    BANK = "BANK"
    BONUS_TEMP = "BONUS_TEMP"
    DECORATION = "DECORATION"
    DWELLING = "DWELLING"
    GUARD = "GUARD"
    HERO = "HERO"
    INFO = "INFO"
    MANA = "MANA"
    MINE = "MINE"
    MINE_SEAL = "MINE_SEAL"
    QUEST_GATE = "QUEST_GATE"
    RESOURCE_PILE = "RESOURCE_PILE"
    REWARD_PICKUP = "REWARD_PICKUP"
    SPECIAL = "SPECIAL"
    SPELL_SKILL = "SPELL_SKILL"
    STAT_PERMANENT = "STAT_PERMANENT"
    TERRAIN_MODIFIER = "TERRAIN_MODIFIER"
    TOWN = "TOWN"
    TRANSPORT = "TRANSPORT"
    UNKNOWN = "UNKNOWN"
    WATER_TRANSPORT = "WATER_TRANSPORT"


VISIT_PURPOSES = (
    Purpose.STAT_PERMANENT,
    Purpose.SPELL_SKILL,
    Purpose.BONUS_TEMP,
    Purpose.MANA,
    Purpose.INFO,
)
COUNTED = (
    Purpose.TOWN,
    Purpose.MINE,
    Purpose.DWELLING,
    Purpose.BANK,
    *VISIT_PURPOSES,
    Purpose.TRANSPORT,
    Purpose.WATER_TRANSPORT,
)

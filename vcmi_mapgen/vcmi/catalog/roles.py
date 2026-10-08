"""The animations behind the object roles the core asks the catalog for: the editor's random
classes, the portals, the border gate colours, the subterranean gate and the spell scroll.

`RANDOM_MONSTERS` and `RANDOM_DWELLINGS` are indexed by level 1..7. `PORTALS` are two-way
monoliths whose one visit tile is their only solid cell, subtypes monolith1..4. Both ends
of a pair share the animation. Heroes III networks every end of one subtype, so a fifth
portal joins an existing network and stays reachable. `SUBTERRANEAN_GATE` has one
un-suffixed sprite.

`CROSSINGS` names the object types a route passes through rather than around. A teleport's
channel also carries its class, so a whirlpool never pairs with a monolith.
`MONSTER_LEVELS` gives the level of each random monster class, and `MONSTER_TYPE` is the
class of a fixed stack.

`VANISH_TYPES` names the object types that leave the map once a hero takes them. VCMI's
object configs flag them `removable` or give them a `removeObject` reward: pickups,
monsters, guards, boats, heroes and the scholar. Every other type lasts, and its visit
tile blocks."""

from vcmi_mapgen.core.catalog import Crossing, Trait
from vcmi_mapgen.core.model.artifact import ArtifactTier

RANDOM_MONSTERS = tuple(f"avwmon{i}" for i in range(1, 8))
RANDOM_ARTIFACT_BY_TIER: dict[ArtifactTier, str] = {
    "treasure": "avarnd1",
    "minor": "avarnd2",
    "major": "avarnd3",
    "relic": "avarnd4",
}
RANDOM_RESOURCE = "avtrndm0"
RANDOM_TOWN = "avcranx0"
RANDOM_DWELLING = "avrcgen0"
RANDOM_DWELLINGS = tuple(f"avrcgen{i}" for i in range(1, 8))
PORTALS = ("avxmn2g0", "avxmn2o0", "avxmn2p0", "avxmn4b0")
BORDER_GATES = tuple((f"avxbgt{i}0", f"avxkey{i}0") for i in range(8))
SUBTERRANEAN_GATE = "avtcave"
CROSSINGS: dict[str, Crossing] = {
    "borderGate": Crossing.GATE,
    "borderGuard": Crossing.GATE,
    "keymasterTent": Crossing.TENT,
    "monolithTwoWay": Crossing.TELEPORT,
    "whirlpool": Crossing.TELEPORT,
    "monolithOneWayEntrance": Crossing.ONE_WAY_IN,
    "monolithOneWayExit": Crossing.ONE_WAY_OUT,
    "subterraneanGate": Crossing.UNDERGROUND,
    "shipyard": Crossing.SHIPYARD,
    "boat": Crossing.BOAT,
}
MONSTER_TYPE = "monster"
MONSTER_LEVELS: dict[str, int] = {f"randomMonsterLevel{lv}": lv for lv in range(1, 8)}
SPELL_SCROLL = "ava0001"
QUEST_GIVER_TYPE = "seerHut"
ABANDONED_MINES = frozenset({"abandoned", "mine"})
VANISH_TYPES = frozenset(
    {
        "artifact",
        "randomArtifact",
        "randomArtifactTreasure",
        "randomArtifactMinor",
        "randomArtifactMajor",
        "randomArtifactRelic",
        "spellScroll",
        "resource",
        "randomResource",
        "monster",
        "randomMonster",
        *MONSTER_LEVELS,
        "pandoraBox",
        "questGuard",
        "borderGuard",
        "boat",
        "campfire",
        "flotsam",
        "seaChest",
        "shipwreckSurvivor",
        "treasureChest",
        "scholar",
        "oceanBottle",
        "event",
        "grail",
        "prison",
        "hero",
        "randomHero",
        "heroPlaceholder",
    }
)
TRAIT_TYPES: dict[Trait, tuple[str, ...]] = {
    Trait.REWARD_BOX: ("pandoraBox",),
    Trait.SCROLL: ("spellScroll",),
    Trait.SHIPYARD: ("shipyard",),
    Trait.ARTIFACT: ("artifact",),
    Trait.SPACED: ("magicWell", "warriorTomb"),
    Trait.LUCK: ("fountainOfFortune", "idolOfFortune"),
    Trait.MEAGER: ("leanTo", "wagon", "warriorTomb", "denOfThieves"),
    Trait.HERO_BOOST: ("learningStone", "gardenOfRevelation", "starAxis"),
    Trait.CHEST: ("treasureChest", "campfire", "pandoraBox"),
    Trait.ZONE_CHEST: ("scholar",),
    Trait.RANDOM_DWELLING: ("randomDwelling", "randomDwellingFaction", "randomDwellingLvl"),
}

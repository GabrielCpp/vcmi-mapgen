"""The animations behind the object roles the core asks the catalog for: the editor's random
classes, the portals, the border gate colours, the subterranean gate and the spell scroll.

`RANDOM_MONSTERS` and `RANDOM_DWELLINGS` are indexed by level 1..7. `PORTALS` are walk-on
two-way monoliths with no blocking cells, subtypes monolith1..4. Both ends of a pair share
the animation. Heroes III networks every end of one subtype, so a fifth portal joins an
existing network and stays reachable. `SUBTERRANEAN_GATE` has one un-suffixed sprite."""

from vcmi_mapgen.core.catalog import ArtifactTier, Trait

RANDOM_MONSTERS = tuple(f"avwmon{i}" for i in range(1, 8))
RANDOM_ARTIFACT = "avarand"
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
SPELL_SCROLL = "ava0001"
QUEST_GIVER_TYPE = "seerHut"
ABANDONED_MINES = frozenset({"abandoned", "mine"})
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

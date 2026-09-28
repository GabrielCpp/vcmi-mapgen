"""Object tables for VCMI/H3 maps: the data the catalog queries.

Lifts raw (class_id, subclass) -> rich identity used by the map-generation model:
  - name:            human class name (from VCMI MapObjectID enum)
  - subtype:         resolved subtype name where canonical (resource/mine/faction), else raw id
  - purpose:         WHY the object exists (drives the "is its placement justified?" logic)
  - relational:      True if the object connects to another location/object (portals, gates...)
  - relational_key:  how the far endpoint is determined (for relational objects)
  - terrain_coupled: True if its placement is strongly tied to terrain type

Purpose tags and relational/terrain flags are HAND-AUTHORED game knowledge -- this is the
small irreducible ontology the data cannot teach (zero negative examples). Subtype *tables*
are canonical H3 orderings, verified against the corpus subclass distributions.

The full CLUSTER -> PURPOSE -> type -> terrain -> leaf tree lives in
``data/ontology/taxonomy.json`` and :func:`taxonomy` loads it once, lazily. It is the ABSOLUTE
object list the VCMI/H3 map editor can place, derived from the object-template table
(objects.txt in the H3 LOD), NOT from the corpus::

    DECORATION -> DECORATION -> mountain -> snow -> avlmtsn3   (terrain-coupled: real terrain)
    QUEST_PAIR -> QUEST_GATE  -> keymasterTent -> land -> red  (colour-keyed: land, leaf = colour)
    VISIBLE    -> TOWN        -> town -> land -> avccast0      (terrain-independent: land/water)

A terrain node holds its leaves as a sorted list of animation DEFs (leaf name == animation), OR
a {colour: animation} dict for colour-keyed quest objects (leaf name == colour).

``data/ontology/leaf_meta.json`` holds per-animation placement metadata (footprint mask +
class/subclass) so the catalog is self-sufficient for tile placement and `.vmap` writing, with
no corpus needed. It maps each lowercase animation DEF to ``[class, subclass, [row, ...]]``;
the rows are B/A/V strings (kit.objects.mask_cells semantics) decoded from the objects.txt
passability/triggers bitfields. :func:`leaf_meta` loads it once, lazily.
``LEAF_TERRAINS`` pins the terrain nodes of animations whose objects.txt terrain masks
misplace them, such as the three magic wells that objects.txt allows on every terrain.
``uv run python -m vcmi_mapgen.cli regen-ontology`` rebuilds both files.
"""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import cast

from vcmi_mapgen.core.model import Mask
from vcmi_mapgen.kit.paths import project_root

type Taxonomy = dict[str, dict[str, dict[str, dict[str, list[str] | dict[str, str]]]]]


@dataclass(frozen=True, slots=True)
class LeafMeta:
    cls: int
    sub: int
    mask: Mask


@dataclass(frozen=True, slots=True)
class ClassInfo:
    name: str
    subtype: str
    purpose: str
    cluster: str
    relational: bool
    relational_key: str | None
    terrain_coupled: bool


def _load_json[T](path: Path, _shape: type[T]) -> T:
    with open(path) as fh:
        return cast(T, json.load(fh))


CLASS_NAMES = {
    int(k): v
    for k, v in _load_json(project_root() / "data" / "objclass_names.json", dict[str, str]).items()
}

# Level/tier classification for the three "graded" H3 entity kinds -- spells (1-5,
# mage-guild tier), artifacts (treasure/minor/major/relic), creatures (1-7, town tier).
# Hand-extracted once (not part of `regenerate()`'s objects.txt-driven pipeline below):
# unlike objects.txt, the source data isn't uniformly available at regen time on an
# arbitrary machine --
#   - MONSTER_LEVELS: VCMI engine source's own config/creatures/*.json ("level" field,
#     already plain JSON, no legacy table involved) -- needs a VCMI *source* checkout.
#   - SPELL_LEVELS / ARTIFACT_TIERS: the level/tier field itself lives in the original
#     H3 game's own legacy text tables (DATA/SPTRAITS.TXT / DATA/ARTRAITS.TXT, inside
#     H3bitmap.lod -- readable via vcmi.formats.lod.lod(data_dir).read(), same mechanism
#     objects.txt uses), but mapping a row to its VCMI identifier requires VCMI *source*
#     config too (config/spells/*.json / config/artifacts.json's "index" field, zipped
#     positionally against the legacy table's file-order rows -- verified by spot-check,
#     since neither file carries the identifier itself). A regen host only has the LOD
#     (this project's existing prerequisite), not a VCMI source tree, so these are
#     checked in as static data instead of re-derived live.
# SPELL_LEVELS/ARTIFACT_TIERS only cover the real, hero-castable/obtainable roster:
# creature-only special abilities (Stone Gaze, Paralyze, ...) and non-random artifacts
# (Spell Book, Spell Scroll, war machines, the Grail) are excluded, not just untiered.
MONSTER_LEVELS = _load_json(project_root() / "data" / "monster_levels.json", dict[str, int])
SPELL_LEVELS = _load_json(project_root() / "data" / "spell_levels.json", dict[str, int])
ARTIFACT_TIERS = _load_json(project_root() / "data" / "artifact_tiers.json", dict[str, str])

# ---- canonical subtype tables (verified vs corpus subclass distributions) ----
RESOURCE = {
    0: "wood",
    1: "mercury",
    2: "ore",
    3: "sulfur",
    4: "crystal",
    5: "gems",
    6: "gold",
    7: "mithril",
}
# mine subclass -> resource it produces (same ordering as resources, 7 = abandoned)
MINE_RES = {
    0: "wood",
    1: "mercury",
    2: "ore",
    3: "sulfur",
    4: "crystal",
    5: "gems",
    6: "gold",
    7: "abandoned",
}
FACTION = {
    0: "castle",
    1: "rampart",
    2: "tower",
    3: "inferno",
    4: "necropolis",
    5: "dungeon",
    6: "stronghold",
    7: "fortress",
    8: "conflux",
}

# ---- purpose taxonomy: class name -> purpose ----
# Categories: TOWN DWELLING MINE RESOURCE_PILE REWARD_PICKUP GUARD TRANSPORT
# WATER_TRANSPORT STAT_PERMANENT BONUS_TEMP MANA SPELL_SKILL INFO BANK QUEST_GATE
# TERRAIN_MODIFIER HERO SPECIAL DECORATION
#
# The 19 fine-grained purposes above are the model's working taxonomy. On top of them
# sits a coarse 4-way *macro-cluster* (see CLUSTERS / cluster_of below) used by the image
# generator: DECORATION (visual), QUEST_PAIR (needs a partner elsewhere), GATE (zone/terrain
# separator), VISIBLE (everything else). The block comments mark each purpose's cluster.
PURPOSE = {
    # [VISIBLE] towns / dwellings
    "TOWN": "TOWN",
    "RANDOM_TOWN": "TOWN",
    "CREATURE_GENERATOR1": "DWELLING",
    "CREATURE_GENERATOR2": "DWELLING",
    "CREATURE_GENERATOR3": "DWELLING",
    "CREATURE_GENERATOR4": "DWELLING",
    "RANDOM_DWELLING": "DWELLING",
    "RANDOM_DWELLING_LVL": "DWELLING",
    "RANDOM_DWELLING_FACTION": "DWELLING",
    "REFUGEE_CAMP": "DWELLING",
    "WAR_MACHINE_FACTORY": "DWELLING",
    # [VISIBLE] economy
    "MINE": "MINE",
    "ABANDONED_MINE": "MINE",
    "RESOURCE": "RESOURCE_PILE",
    "RANDOM_RESOURCE": "RESOURCE_PILE",
    "WINDMILL": "MINE",
    "WATER_WHEEL": "MINE",
    "MAGIC_SPRING": "MINE",
    "MYSTICAL_GARDEN": "MINE",
    "LEAN_TO": "REWARD_PICKUP",
    "TRADING_POST": "SPECIAL",
    "TRADING_POST_SNOW": "SPECIAL",
    "MARKET_OF_TIME": "SPECIAL",
    # [VISIBLE] reward pickups
    "TREASURE_CHEST": "REWARD_PICKUP",
    "CAMPFIRE": "REWARD_PICKUP",
    "FLOTSAM": "REWARD_PICKUP",
    "SEA_CHEST": "REWARD_PICKUP",
    "SHIPWRECK_SURVIVOR": "REWARD_PICKUP",
    "CORPSE": "REWARD_PICKUP",
    "SKULL": "REWARD_PICKUP",
    "WARRIORS_TOMB": "REWARD_PICKUP",
    "WAGON": "REWARD_PICKUP",
    "SCHOLAR": "REWARD_PICKUP",
    "ARTIFACT": "REWARD_PICKUP",
    "RANDOM_ART": "REWARD_PICKUP",
    "RANDOM_TREASURE_ART": "REWARD_PICKUP",
    "RANDOM_MINOR_ART": "REWARD_PICKUP",
    "RANDOM_MAJOR_ART": "REWARD_PICKUP",
    "RANDOM_RELIC_ART": "REWARD_PICKUP",
    "SPELL_SCROLL": "REWARD_PICKUP",
    "PANDORAS_BOX": "REWARD_PICKUP",
    "GRAIL": "SPECIAL",
    # [VISIBLE] guards
    "MONSTER": "GUARD",
    "RANDOM_MONSTER": "GUARD",
    "RANDOM_MONSTER_L1": "GUARD",
    "RANDOM_MONSTER_L2": "GUARD",
    "RANDOM_MONSTER_L3": "GUARD",
    "RANDOM_MONSTER_L4": "GUARD",
    "RANDOM_MONSTER_L5": "GUARD",
    "RANDOM_MONSTER_L6": "GUARD",
    "RANDOM_MONSTER_L7": "GUARD",
    # [VISIBLE] guarded combat banks
    "CREATURE_BANK": "BANK",
    "DERELICT_SHIP": "BANK",
    "CRYPT": "BANK",
    "SHIPWRECK": "BANK",
    "DRAGON_UTOPIA": "BANK",
    "PYRAMID": "BANK",
    # [QUEST_PAIR] transport portals (relational: paired endpoints)
    "MONOLITH_ONE_WAY_ENTRANCE": "TRANSPORT",
    "MONOLITH_ONE_WAY_EXIT": "TRANSPORT",
    "MONOLITH_TWO_WAY": "TRANSPORT",
    "SUBTERRANEAN_GATE": "TRANSPORT",
    "WHIRLPOOL": "TRANSPORT",
    "SHIPYARD": "WATER_TRANSPORT",
    "BOAT": "WATER_TRANSPORT",
    "LIGHTHOUSE": "WATER_TRANSPORT",
    # [VISIBLE] permanent stat boosts
    "LEARNING_STONE": "STAT_PERMANENT",
    "TREE_OF_KNOWLEDGE": "STAT_PERMANENT",
    "MARLETTO_TOWER": "STAT_PERMANENT",
    "STAR_AXIS": "STAT_PERMANENT",
    "GARDEN_OF_REVELATION": "STAT_PERMANENT",
    "MERCENARY_CAMP": "STAT_PERMANENT",
    "SCHOOL_OF_MAGIC": "STAT_PERMANENT",
    "SCHOOL_OF_WAR": "STAT_PERMANENT",
    "LIBRARY_OF_ENLIGHTENMENT": "STAT_PERMANENT",
    "ARENA": "STAT_PERMANENT",
    "HILL_FORT": "STAT_PERMANENT",
    "BORDERGUARD_CAMP": "STAT_PERMANENT",
    # [VISIBLE] temporary bonuses (luck/morale/movement)
    "IDOL_OF_FORTUNE": "BONUS_TEMP",
    "FOUNTAIN_OF_FORTUNE": "BONUS_TEMP",
    "FOUNTAIN_OF_YOUTH": "BONUS_TEMP",
    "RALLY_FLAG": "BONUS_TEMP",
    "OASIS": "BONUS_TEMP",
    "WATERING_HOLE": "BONUS_TEMP",
    "BUOY": "BONUS_TEMP",
    "MERMAID": "BONUS_TEMP",
    "SWAN_POND": "BONUS_TEMP",
    "FAERIE_RING": "BONUS_TEMP",
    "TEMPLE": "BONUS_TEMP",
    "STABLES": "BONUS_TEMP",
    "WELL_OF_YOUTH": "BONUS_TEMP",
    # [VISIBLE] mana
    "MAGIC_WELL": "MANA",
    # [VISIBLE] spell / skill
    "SHRINE_OF_MAGIC_INCANTATION": "SPELL_SKILL",
    "SHRINE_OF_MAGIC_GESTURE": "SPELL_SKILL",
    "SHRINE_OF_MAGIC_THOUGHT": "SPELL_SKILL",
    "WITCH_HUT": "SPELL_SKILL",
    "MAGIC_SPRING_SPELL": "SPELL_SKILL",
    # [VISIBLE] info
    "OBELISK": "INFO",
    "SIGN": "INFO",
    "OCEAN_BOTTLE": "INFO",
    "REDWOOD_OBSERVATORY": "INFO",
    "PILLAR_OF_FIRE": "INFO",
    "EYE_OF_MAGI": "INFO",
    "HUT_OF_MAGI": "INFO",
    "CARTOGRAPHER": "INFO",
    # [GATE / QUEST_PAIR] quest gates -- splits by object type:
    #   borderGate/borderGuard/questGuard -> GATE; seerHut/keymasterTent -> QUEST_PAIR
    "SEER_HUT": "QUEST_GATE",
    "QUEST_GUARD": "QUEST_GATE",
    "BORDERGUARD": "QUEST_GATE",
    "BORDER_GATE": "QUEST_GATE",
    "KEYMASTER": "QUEST_GATE",
    # [VISIBLE] special terrain modifiers
    "MAGIC_PLAINS1": "TERRAIN_MODIFIER",
    "MAGIC_PLAINS2": "TERRAIN_MODIFIER",
    "CURSED_GROUND1": "TERRAIN_MODIFIER",
    "CURSED_GROUND2": "TERRAIN_MODIFIER",
    "CLOVER_FIELD": "TERRAIN_MODIFIER",
    "EVIL_FOG": "TERRAIN_MODIFIER",
    "HOLY_GROUNDS": "TERRAIN_MODIFIER",
    "LUCID_POOLS": "TERRAIN_MODIFIER",
    "FIERY_FIELDS": "TERRAIN_MODIFIER",
    "ROCKLANDS": "TERRAIN_MODIFIER",
    "MAGIC_CLOUDS": "TERRAIN_MODIFIER",
    # [VISIBLE] heroes / structural
    "HERO": "HERO",
    "RANDOM_HERO": "HERO",
    "PRISON": "HERO",
    "HERO_PLACEHOLDER": "HERO",
    "GARRISON": "SPECIAL",
    "GARRISON2": "SPECIAL",
    "EVENT": "SPECIAL",
    "FREELANCERS_GUILD": "SPECIAL",
    # [VISIBLE] trade / utility buildings
    "DEN_OF_THIEVES": "INFO",
    "COVER_OF_DARKNESS": "INFO",
    "BLACK_MARKET": "SPECIAL",
    "ALTAR_OF_SACRIFICE": "SPECIAL",
    "UNIVERSITY": "SPELL_SKILL",
    "SANCTUARY": "SPECIAL",
    "TAVERN": "SPECIAL",
    "DEN_OF_THIEVES2": "INFO",
    # [VISIBLE] water bonus / terrain
    "FAVORABLE_WINDS": "TERRAIN_MODIFIER",
    "SIRENS": "BONUS_TEMP",
}

# ---- macro-clusters: coarse 4-way grouping used by the image generator ----
# A purpose maps wholesale to a cluster, EXCEPT QUEST_GATE which splits per object:
#   borderGate / borderGuard / questGuard -> GATE  (a physical separator between zones/terrains)
#   seerHut / keymasterTent               -> QUEST_PAIR  (the half that implies a partner elsewhere)
CLUSTERS = ("DECORATION", "VISIBLE", "GATE", "QUEST_PAIR")
GATE_TYPES = {"borderGate", "borderGuard", "questGuard"}  # objlib `type` strings
GATE_NAMES = {"BORDER_GATE", "BORDERGUARD", "QUEST_GUARD"}  # ontology enum names


# relational objects -> how the far endpoint is determined
RELATIONAL = {
    "MONOLITH_TWO_WAY": "same-subclass network (any other two-way monolith of equal subclass)",
    "MONOLITH_ONE_WAY_ENTRANCE": "matching one-way exit of equal subclass",
    "MONOLITH_ONE_WAY_EXIT": "matching one-way entrance of equal subclass",
    "SUBTERRANEAN_GATE": "nearest gate on the opposite level",
    "WHIRLPOOL": "another whirlpool (water network)",
    "BORDERGUARD": "keymaster tent of same subclass (colour)",
    "BORDER_GATE": "keymaster tent of same subclass (colour)",
    "KEYMASTER": "opens borderguards/gates of same subclass (colour)",
    "SEER_HUT": "quest target object (by id, stored in body)",
}

# terrain-coupled gameplay objects (placement strongly tied to terrain; most decoration also is)
TERRAIN_COUPLED = {
    "MINE",
    "ABANDONED_MINE",
    "TERRAIN_MODIFIER",
    "SHIPYARD",
    "LIGHTHOUSE",
    "WHIRLPOOL",
    "BOAT",
    "FLOTSAM",
    "SEA_CHEST",
    "SHIPWRECK",
    "SHIPWRECK_SURVIVOR",
    "BUOY",
    "MERMAID",
    "DERELICT_SHIP",
    "CARTOGRAPHER",
    "REDWOOD_OBSERVATORY",
    "SIGN",
    "PILLAR_OF_FIRE",
}


DECOR_NAMES = {
    "MOUNTAIN",
    "OAK_TREES",
    "PINE_TREES",
    "ROCK",
    "DEAD_VEGETATION",
    "SHRUB",
    "REEF",
    "TREES",
    "FLOWERS",
    "CRATER",
    "CACTUS",
    "LAVA_FLOW",
    "MUSHROOMS",
    "LAKE",
    "STUMP",
    "HOLE",
    "HEDGE",
    "KELP",
    "WILLOW_TREES",
    "YUCCA_TREES",
    "VOLCANO",
    "SAND_DUNE",
    "SAND_PIT",
    "CANYON",
    "MOSS",
    "BUSH",
    "PALM_TREE",
    "PLANT",
    "RIVER_DELTA",
    "FROZEN_LAKE",
    "OUTCROPPING",
    "MOUND",
    "LOG",
    "LAVA_LAKE",
    "SKULL",
    "CORPSE_DECO",
    "MANDRAKE",
    "FLOWERS2",
    "TAR_PIT",
    "GAZEBO_DECO",
    # AB decorative classes (verified against objects.txt DEFs + sprite renders):
    # avllk1r / avlswt* / avlxds* avlxdt* avlxgr* avlxro* avlxsu* avlxsw*
    "LAKE_2",
    "TREES_2",
    "DESERT_HILLS",
    "DIRT_HILLS",
    "GRASS_HILLS",
    "ROUGH_HILLS",
    "SUBTERRANEAN_ROCKS",
    "SWAMP_FOLIAGE",
}


TERRAIN_NAMES = {
    0: "dirt",
    1: "sand",
    2: "grass",
    3: "snow",
    4: "swamp",
    5: "rough",
    6: "subterr",
    7: "lava",
    8: "water",
    9: "rock",
}
# Objects keyed by player colour (quest lock/key). Colour is terrain-independent, so they bucket
# under a single "land" terrain node and their leaves are named by colour (all 8 enumerated).
COLOR_KEYED_NAMES = {"BORDER_GATE", "BORDERGUARD", "KEYMASTER"}
# Types whose subtype is a meaningful identity (a town's faction) rather than a colour: the leaf is
# named by the readable subtype so the catalog branches by faction (castle/rampart/...) instead of
# dumping every faction's cryptic animation flat in one node.
SUBTYPE_KEYED_NAMES = {"TOWN"}
# objects.txt subclass -> gate/key colour (matches the avx{key,bor,bgt}NN DEF suffix /10).
GATE_COLORS = {
    0: "lblue",
    1: "green",
    2: "red",
    3: "dblue",
    4: "brown",
    5: "purple",
    6: "white",
    7: "black",
}

LEAF_TERRAINS = {
    "avxwelr0": ("dirt", "lava", "rough", "sand", "subterr"),
    "avxwelg0": ("grass", "swamp"),
    "avxwlsn0": ("snow",),
}


def table_path(name: str) -> Path:
    return project_root() / "data" / "ontology" / name


@cache
def taxonomy() -> Taxonomy:
    """The CLUSTER->PURPOSE->type->terrain->leaf tree from ``data/ontology/taxonomy.json``."""
    with open(table_path("taxonomy.json")) as fh:
        return cast(Taxonomy, json.load(fh))


@cache
def leaf_meta() -> dict[str, LeafMeta]:
    """Per-animation placement metadata from ``data/ontology/leaf_meta.json``."""
    with open(table_path("leaf_meta.json")) as fh:
        raw = cast(dict[str, tuple[int, int, list[str]]], json.load(fh))
    return {anim: LeafMeta(cls, sub, tuple(rows)) for anim, (cls, sub, rows) in raw.items()}

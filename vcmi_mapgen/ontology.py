"""Object ontology for VCMI/H3 maps.

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
"""

import json
import os
import struct
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from random import Random
from typing import cast

from vcmi_mapgen.kit import vcmi_config
from vcmi_mapgen.kit.lod import lod
from vcmi_mapgen.kit.paths import project_root
from vcmi_mapgen.models import Identity, Mask

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


@dataclass(frozen=True, slots=True)
class _Indexes:
    anim_terrains: dict[str, set[str]]
    anim_category: dict[str, str]
    veg_categories: list[str]
    decor_by_terrain: dict[str, list[str]]
    gameplay_by_tp: dict[tuple[str, str], list[str]]


def _load_json[T](path: Path, _shape: type[T]) -> T:
    with open(path) as fh:
        return cast(T, json.load(fh))


_HERE = os.path.dirname(os.path.abspath(__file__))
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
#     H3bitmap.lod -- readable via kit.lod.lod().read(), same mechanism
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


def cluster_of(purpose: str, name: str | None = None, type_: str | None = None) -> str:
    """Macro-cluster for an object, from its purpose plus (when QUEST_GATE) its enum name
    or objlib `type`. Usable from both the enum-name path (resolve) and the objlib-type
    path (the catalog renderer)."""
    if purpose == "DECORATION":
        return "DECORATION"
    if purpose == "TRANSPORT":
        return "QUEST_PAIR"
    if purpose == "QUEST_GATE":
        if name in GATE_NAMES or type_ in GATE_TYPES:
            return "GATE"
        return "QUEST_PAIR"
    return "VISIBLE"


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


# class ids that are pure visual obstacles (incl. the once-unnamed AB decor classes
# 177/199/206-211, now named LAKE_2 / TREES_2 / *_HILLS / SUBTERRANEAN_ROCKS / SWAMP_FOLIAGE)
def _is_decoration(name: str) -> bool:
    if name.startswith("CLASS_"):  # enum gap -> decorative obstacle
        return True
    return name in DECOR_NAMES


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


def name_of(cid: int) -> str:
    return CLASS_NAMES.get(cid, f"CLASS_{cid}")


def resolve(cid: int, subclass: int) -> ClassInfo:
    name = name_of(cid)
    # subtype resolution
    if name in ("RESOURCE", "RANDOM_RESOURCE"):
        subtype = RESOURCE.get(subclass, str(subclass)) if name == "RESOURCE" else "random"
    elif name in ("MINE", "ABANDONED_MINE"):
        subtype = MINE_RES.get(subclass, str(subclass))
    elif name == "TOWN":
        subtype = FACTION.get(subclass, str(subclass))
    elif name == "RANDOM_TOWN":
        subtype = "random"
    else:
        subtype = str(subclass)
    decor = _is_decoration(name)
    purpose = "DECORATION" if decor else PURPOSE.get(name, "UNKNOWN")
    return ClassInfo(
        name=name,
        subtype=subtype,
        purpose=purpose,
        cluster=cluster_of(purpose, name=name),
        relational=name in RELATIONAL,
        relational_key=RELATIONAL.get(name),
        terrain_coupled=(
            purpose in ("MINE", "TERRAIN_MODIFIER", "WATER_TRANSPORT")
            or name in TERRAIN_COUPLED
            or decor
        ),
    )


# ---------------------------------------------------------------------------
# Full taxonomy tree: CLUSTER -> PURPOSE -> type -> terrain -> leaf
# ---------------------------------------------------------------------------
# The hand-authored layers above (cluster, purpose) are the irreducible ontology; the lower layers
# (type -> terrain -> concrete sprite) complete the tree, every parent->child edge down to the leaf
# sprite. The full tree is HARDCODED below as TAXONOMY -- it is the single source of truth for the
# catalog renderer (cli.py render-ontology). It is the ABSOLUTE object list the VCMI/H3 map
# editor can place: derived from the authoritative object-template table (objects.txt in the H3
# LOD),
# NOT from the corpus. Regenerate in place with `python -m vcmi_mapgen.ontology --regen`.
#
#   DECORATION -> DECORATION -> mountain -> snow -> avlmtsn3   (terrain-coupled: real terrain)
#   QUEST_PAIR -> QUEST_GATE  -> keymasterTent -> land -> red  (colour-keyed: land, leaf = colour)
#   VISIBLE    -> TOWN        -> town -> land -> avccast0      (terrain-independent: land/water)
#
# A terrain node holds its leaves as a sorted list of animation DEFs (leaf name == animation), OR a
# {colour: animation} dict for colour-keyed quest objects (leaf name == colour).

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
TREE_CACHE = os.path.join(os.path.dirname(_HERE), "out", "ontology_tree.json")

# === BEGIN GENERATED TAXONOMY (regenerate with `python -m vcmi_mapgen.ontology --regen`) ===
TAXONOMY: Taxonomy = {
    "DECORATION": {
        "DECORATION": {
            "CACTUS": {
                "rough": ["avlca1r0", "avlca2r0"],
                "sand": [
                    "avlca010",
                    "avlca020",
                    "avlca030",
                    "avlca040",
                    "avlca050",
                    "avlca060",
                    "avlca070",
                    "avlca080",
                    "avlca090",
                    "avlca100",
                    "avlca110",
                    "avlca120",
                    "avlca130",
                ],
            },
            "CANYON": {"rough": ["avlglly0"]},
            "CRATER": {
                "dirt": ["avlct1d0", "avlct2d0", "avlct3d0", "avlct4d0", "avlct5d0", "avlctrd0"],
                "grass": [
                    "avlct1g0",
                    "avlct2g0",
                    "avlct3g0",
                    "avlct4g0",
                    "avlct5g0",
                    "avlct6g0",
                    "avlctrg0",
                ],
                "lava": [
                    "avlc10l0",
                    "avlc11l0",
                    "avlc12l0",
                    "avlc13l0",
                    "avlc14l0",
                    "avlct1l0",
                    "avlct2l0",
                    "avlct3l0",
                    "avlct4l0",
                    "avlct5l0",
                    "avlct6l0",
                    "avlct7l0",
                    "avlct8l0",
                    "avlct9l0",
                    "avlctrl0",
                ],
                "rough": [
                    "avlct1r0",
                    "avlct2r0",
                    "avlct3r0",
                    "avlct4r0",
                    "avlct5r0",
                    "avlct6r0",
                    "avlct7r0",
                    "avlct8r0",
                    "avlct9r0",
                    "avlctrr0",
                ],
                "sand": ["avlctds0"],
                "snow": ["avlctsn0"],
                "subterr": ["avlct1u0", "avlct2u0", "avlct3u0", "avlct4u0", "avlct5u0"],
                "swamp": ["avlctrs0"],
            },
            "DEAD_VEGETATION": {
                "lava": [
                    "avldead0",
                    "avldead1",
                    "avldead2",
                    "avldead3",
                    "avldead4",
                    "avldead5",
                    "avldead6",
                    "avldead7",
                ],
                "snow": [
                    "avld1sn0",
                    "avld2sn0",
                    "avld3sn0",
                    "avld4sn0",
                    "avld5sn0",
                    "avld6sn0",
                    "avld7sn0",
                    "avld8sn0",
                    "avld9sn0",
                    "avlddsn0",
                    "avlddsn1",
                    "avlddsn2",
                    "avlddsn3",
                    "avlddsn4",
                    "avlddsn5",
                    "avlddsn6",
                    "avlddsn7",
                ],
                "subterr": [
                    "avldead0",
                    "avldead1",
                    "avldead2",
                    "avldead3",
                    "avldead4",
                    "avldead5",
                    "avldead6",
                    "avldead7",
                ],
                "swamp": [
                    "avldead0",
                    "avldead1",
                    "avldead2",
                    "avldead3",
                    "avldead4",
                    "avldead5",
                    "avldead6",
                    "avldead7",
                    "avldt1s0",
                    "avldt2s0",
                    "avldt3s0",
                    "avlswp60",
                    "avlswp70",
                ],
            },
            "DESERT_HILLS": {
                "sand": [
                    "avlxds01",
                    "avlxds02",
                    "avlxds03",
                    "avlxds04",
                    "avlxds05",
                    "avlxds06",
                    "avlxds07",
                    "avlxds08",
                    "avlxds09",
                    "avlxds10",
                    "avlxds11",
                    "avlxds12",
                ]
            },
            "DIRT_HILLS": {
                "dirt": [
                    "avlxdt00",
                    "avlxdt01",
                    "avlxdt02",
                    "avlxdt03",
                    "avlxdt04",
                    "avlxdt05",
                    "avlxdt06",
                    "avlxdt07",
                    "avlxdt08",
                    "avlxdt09",
                    "avlxdt10",
                    "avlxdt11",
                ]
            },
            "FLOWERS": {
                "dirt": [
                    "avlfl1d0",
                    "avlfl2d0",
                    "avlfl3d0",
                    "avlfl4d0",
                    "avlfl5d0",
                    "avlfl6d0",
                    "avlfl7d0",
                    "avlfl8d0",
                    "avlfl9d0",
                ],
                "grass": [
                    "avlf01g0",
                    "avlf02g0",
                    "avlf03g0",
                    "avlf04g0",
                    "avlf05g0",
                    "avlf06g0",
                    "avlf07g0",
                    "avlf08g0",
                    "avlf09g0",
                    "avlf10g0",
                    "avlf11g0",
                    "avlf12g0",
                ],
            },
            "FROZEN_LAKE": {"snow": ["avlflk10", "avlflk20", "avlflk30"]},
            "GRASS_HILLS": {
                "grass": [
                    "avlxgr01",
                    "avlxgr02",
                    "avlxgr03",
                    "avlxgr04",
                    "avlxgr05",
                    "avlxgr06",
                    "avlxgr07",
                    "avlxgr08",
                    "avlxgr09",
                    "avlxgr10",
                    "avlxgr11",
                    "avlxgr12",
                ]
            },
            "HOLE": {
                "dirt": ["avlhold0"],
                "grass": ["avlholg0"],
                "lava": ["avlholl0"],
                "rough": ["avlholr0"],
                "sand": ["avlhlds0"],
                "snow": ["avlhlsn0"],
                "subterr": ["avlholx0"],
                "swamp": ["avlhols0"],
            },
            "KELP": {"water": ["avlklp10", "avlklp20"]},
            "LAKE": {
                "dirt": ["avllk1d0", "avllk2d0", "avllk3d0"],
                "grass": ["avllk1g0", "avllk2g0", "avllk3g0"],
                "subterr": ["avllk1u0", "avllk2u0", "avllk3u0"],
                "swamp": ["avllk1s0", "avllk2s0", "avllk3s0", "avlswp50"],
            },
            "LAKE_2": {"rough": ["avllk1r"]},
            "LAVA_FLOW": {
                "lava": [
                    "avllav20",
                    "avllav30",
                    "avllav40",
                    "avllav50",
                    "avllav60",
                    "avllav70",
                    "avllav80",
                    "avllav90",
                    "avllv100",
                    "avllv110",
                    "avllv120",
                    "avllv130",
                    "avllv140",
                    "avllv150",
                    "avllv160",
                    "avllv170",
                    "avllv180",
                    "avllv190",
                    "avllv200",
                    "avllv210",
                    "avllv220",
                    "avllv230",
                    "avllv240",
                    "avllv250",
                    "avllv260",
                ],
                "subterr": ["avllv1u0", "avllv2u0", "avllv3u0"],
            },
            "LAVA_LAKE": {"lava": ["avllav10"], "subterr": ["avlllk10", "avlllk20"]},
            "LOG": {"dirt": ["avldlog"], "grass": ["avldlog"], "rough": ["avldlog"]},
            "MANDRAKE": {"swamp": ["avlman10", "avlman20", "avlman30", "avlman40", "avlman50"]},
            "MOSS": {"swamp": ["avlmoss0"]},
            "MOUND": {
                "dirt": ["avlmd1d0", "avlmd2d0"],
                "grass": ["avlmd1g0", "avlmd2g0"],
                "rough": ["avlmd1r0", "avlmd2r0", "avlmd3r0"],
            },
            "MOUNTAIN": {
                "dirt": [
                    "avlmtdr1",
                    "avlmtdr2",
                    "avlmtdr3",
                    "avlmtdr4",
                    "avlmtdr5",
                    "avlmtdr6",
                    "avlmtdr7",
                    "avlmtdr8",
                ],
                "grass": [
                    "avlmtgn0",
                    "avlmtgn1",
                    "avlmtgn2",
                    "avlmtgn3",
                    "avlmtgn4",
                    "avlmtgn5",
                    "avlmtgr1",
                    "avlmtgr2",
                    "avlmtgr3",
                    "avlmtgr4",
                    "avlmtgr5",
                    "avlmtgr6",
                ],
                "lava": ["avlmtvo1", "avlmtvo2", "avlmtvo3", "avlmtvo4", "avlmtvo5", "avlmtvo6"],
                "rough": ["avlmtrf1", "avlmtrf2", "avlmtrf3", "avlmtrf4", "avlmtrf5", "avlmtrf6"],
                "sand": ["avlmtds1", "avlmtds2", "avlmtds3", "avlmtds4", "avlmtds5", "avlmtds6"],
                "snow": ["avlmtsn1", "avlmtsn2", "avlmtsn3", "avlmtsn4", "avlmtsn5", "avlmtsn6"],
                "subterr": ["avlmtsb0", "avlmtsb1", "avlmtsb2", "avlmtsb3", "avlmtsb4", "avlmtsb5"],
                "swamp": ["avlmtsw1", "avlmtsw2", "avlmtsw3", "avlmtsw4", "avlmtsw5", "avlmtsw6"],
            },
            "MUSHROOMS": {
                "subterr": [
                    "avlms010",
                    "avlms020",
                    "avlms030",
                    "avlms040",
                    "avlms050",
                    "avlms060",
                    "avlms070",
                    "avlms080",
                    "avlms090",
                    "avlms100",
                    "avlms110",
                    "avlms120",
                ]
            },
            "OAK_TREES": {
                "dirt": [
                    "avlautr0",
                    "avlautr1",
                    "avlautr2",
                    "avlautr3",
                    "avlautr4",
                    "avlautr5",
                    "avlautr6",
                    "avlautr7",
                ],
                "grass": [
                    "avlautr0",
                    "avlautr1",
                    "avlautr2",
                    "avlautr3",
                    "avlautr4",
                    "avlautr5",
                    "avlautr6",
                    "avlautr7",
                    "avlsptr0",
                    "avlsptr1",
                    "avlsptr2",
                    "avlsptr3",
                    "avlsptr4",
                    "avlsptr5",
                    "avlsptr6",
                    "avlsptr7",
                    "avlsptr8",
                ],
                "swamp": [
                    "avlsptr0",
                    "avlsptr1",
                    "avlsptr2",
                    "avlsptr3",
                    "avlsptr4",
                    "avlsptr5",
                    "avlsptr6",
                    "avlsptr7",
                    "avlsptr8",
                ],
            },
            "OUTCROPPING": {
                "dirt": ["avloc1d0", "avloc2d0", "avloc3d0"],
                "grass": ["avloc1g0", "avloc2g0", "avloc3g0"],
                "rough": ["avloc1r0", "avloc2r0", "avloc3r0", "avloc4r0"],
                "snow": ["avlo1sn0", "avlo2sn0", "avlo3sn0"],
                "subterr": ["avloc1u0", "avloc2u0", "avloc3u0", "avloc4u0"],
            },
            "PINE_TREES": {
                "dirt": [
                    "avlpntr0",
                    "avlpntr1",
                    "avlpntr2",
                    "avlpntr3",
                    "avlpntr4",
                    "avlpntr5",
                    "avlpntr6",
                    "avlpntr7",
                ],
                "grass": [
                    "avlpntr0",
                    "avlpntr1",
                    "avlpntr2",
                    "avlpntr3",
                    "avlpntr4",
                    "avlpntr5",
                    "avlpntr6",
                    "avlpntr7",
                ],
                "snow": [
                    "avlsntr0",
                    "avlsntr1",
                    "avlsntr2",
                    "avlsntr3",
                    "avlsntr4",
                    "avlsntr5",
                    "avlsntr6",
                    "avlsntr7",
                ],
            },
            "REEF": {
                "water": ["avlref10", "avlref20", "avlref30", "avlref40", "avlref50", "avlref60"]
            },
            "RIVER_DELTA": {
                "dirt": [
                    "clrdelt1",
                    "clrdelt2",
                    "clrdelt3",
                    "clrdelt4",
                    "muddelt1",
                    "muddelt2",
                    "muddelt3",
                    "muddelt4",
                ],
                "grass": [
                    "clrdelt1",
                    "clrdelt2",
                    "clrdelt3",
                    "clrdelt4",
                    "muddelt1",
                    "muddelt2",
                    "muddelt3",
                    "muddelt4",
                ],
                "lava": [
                    "clrdelt1",
                    "clrdelt2",
                    "clrdelt3",
                    "clrdelt4",
                    "lavdelt1",
                    "lavdelt2",
                    "lavdelt3",
                    "lavdelt4",
                    "muddelt1",
                    "muddelt2",
                    "muddelt3",
                    "muddelt4",
                ],
                "rough": [
                    "clrdelt1",
                    "clrdelt2",
                    "clrdelt3",
                    "clrdelt4",
                    "muddelt1",
                    "muddelt2",
                    "muddelt3",
                    "muddelt4",
                ],
                "sand": [
                    "clrdelt1",
                    "clrdelt2",
                    "clrdelt3",
                    "clrdelt4",
                    "muddelt1",
                    "muddelt2",
                    "muddelt3",
                    "muddelt4",
                ],
                "snow": [
                    "clrdelt1",
                    "clrdelt2",
                    "clrdelt3",
                    "clrdelt4",
                    "icedelt1",
                    "icedelt2",
                    "icedelt3",
                    "icedelt4",
                    "muddelt1",
                    "muddelt2",
                    "muddelt3",
                    "muddelt4",
                ],
                "subterr": [
                    "clrdelt1",
                    "clrdelt2",
                    "clrdelt3",
                    "clrdelt4",
                    "muddelt1",
                    "muddelt2",
                    "muddelt3",
                    "muddelt4",
                ],
                "swamp": [
                    "clrdelt1",
                    "clrdelt2",
                    "clrdelt3",
                    "clrdelt4",
                    "muddelt1",
                    "muddelt2",
                    "muddelt3",
                    "muddelt4",
                ],
            },
            "ROCK": {
                "dirt": ["avlrd01", "avlrd02", "avlrd04", "avlrk3d0", "avlrk5d0"],
                "grass": [
                    "avlrg01",
                    "avlrg02",
                    "avlrg03",
                    "avlrg04",
                    "avlrg05",
                    "avlrg06",
                    "avlrg07",
                    "avlrg08",
                    "avlrg09",
                    "avlrg10",
                    "avlrg11",
                ],
                "rough": [
                    "avlbuzr0",
                    "avlr02r0",
                    "avlr03r0",
                    "avlr04r0",
                    "avlr06r0",
                    "avlr07r0",
                    "avlr08r0",
                    "avlr09r0",
                    "avlr10r0",
                    "avlr11r0",
                    "avlr12r0",
                    "avlr13r0",
                    "avlr14r0",
                    "avlr15r0",
                    "avlrr01",
                    "avlrr05",
                ],
                "snow": [
                    "avlr1sn0",
                    "avlr2sn0",
                    "avlr3sn0",
                    "avlr4sn0",
                    "avlr5sn0",
                    "avlr6sn0",
                    "avlr7sn0",
                    "avlr8sn0",
                ],
                "subterr": [
                    "avlr01u0",
                    "avlr02u0",
                    "avlr03u0",
                    "avlr04u0",
                    "avlr05u0",
                    "avlr06u0",
                    "avlr07u0",
                    "avlr08u0",
                    "avlr09u0",
                    "avlr10u0",
                    "avlr11u0",
                    "avlr12u0",
                    "avlr13u0",
                    "avlr14u0",
                    "avlr15u0",
                    "avlr16u0",
                    "avlstg10",
                    "avlstg20",
                    "avlstg30",
                    "avlstg40",
                    "avlstg50",
                    "avlstg60",
                ],
                "swamp": ["avlrk1s0", "avlrk2s0", "avlrk3s0", "avlrk4s0"],
                "water": ["avlrk1w0", "avlrk2w0", "avlrk3w0", "avlrk4w0"],
            },
            "ROUGH_HILLS": {
                "rough": [
                    "avlxro01",
                    "avlxro02",
                    "avlxro03",
                    "avlxro04",
                    "avlxro05",
                    "avlxro06",
                    "avlxro07",
                    "avlxro08",
                    "avlxro09",
                    "avlxro10",
                    "avlxro11",
                    "avlxro12",
                ]
            },
            "SAND_DUNE": {"sand": ["avldun10", "avldun20", "avldun30"]},
            "SAND_PIT": {"sand": ["avlspit0"]},
            "SHRUB": {
                "dirt": [
                    "avlsh1d0",
                    "avlsh2d0",
                    "avlsh3d0",
                    "avlsh4d0",
                    "avlsh5d0",
                    "avlsh6d0",
                    "avlsh7d0",
                    "avlsh8d0",
                ],
                "grass": ["avlsh1g0", "avlsh2g0", "avlsh3g0", "avlsh4g0", "avlsh5g0", "avlsh6g0"],
                "rough": [
                    "avlsh1r0",
                    "avlsh2r0",
                    "avlsh3r0",
                    "avlsh4r0",
                    "avlsh5r0",
                    "avlsh6r0",
                    "avlsh7r0",
                    "avlsh8r0",
                    "avlsh9r0",
                ],
                "snow": ["avls1sn0", "avls2sn0", "avls3sn0"],
                "swamp": [
                    "avls01s0",
                    "avls02s0",
                    "avls03s0",
                    "avls04s0",
                    "avls05s0",
                    "avls06s0",
                    "avls07s0",
                    "avls08s0",
                    "avls09s0",
                    "avls10s0",
                    "avls11s0",
                    "avlswp10",
                    "avlswp20",
                    "avlswp30",
                    "avlswp40",
                ],
            },
            "SKULL": {"rough": ["avlskul0"], "sand": ["avlskul0"]},
            "STUMP": {
                "dirt": ["avlstm1", "avlstm2", "avlstm3"],
                "grass": ["avlstm1", "avlstm2", "avlstm3"],
                "rough": ["avlstm1", "avlstm2", "avlstm3"],
                "snow": ["avlp1sn0", "avlp2sn0"],
            },
            "SUBTERRANEAN_ROCKS": {
                "subterr": [
                    "avlxsu01",
                    "avlxsu02",
                    "avlxsu03",
                    "avlxsu04",
                    "avlxsu05",
                    "avlxsu06",
                    "avlxsu07",
                    "avlxsu08",
                    "avlxsu09",
                    "avlxsu10",
                    "avlxsu11",
                    "avlxsu12",
                ]
            },
            "SWAMP_FOLIAGE": {
                "swamp": [
                    "avlxsw01",
                    "avlxsw02",
                    "avlxsw03",
                    "avlxsw04",
                    "avlxsw05",
                    "avlxsw06",
                    "avlxsw07",
                    "avlxsw08",
                    "avlxsw09",
                    "avlxsw10",
                    "avlxsw11",
                ]
            },
            "TREES": {
                "dirt": ["avltr1d0", "avltr2d0", "avltr3d0"],
                "grass": [
                    "avlswmp0",
                    "avlswmp1",
                    "avlswmp2",
                    "avlswmp3",
                    "avlswmp4",
                    "avlswmp5",
                    "avlswmp6",
                    "avlswmp7",
                    "avltr1d0",
                    "avltr2d0",
                    "avltr3d0",
                    "avlwlw10",
                    "avlwlw20",
                    "avlwlw30",
                ],
                "rough": ["avlroug0", "avlroug1", "avlroug2", "avlyuc10", "avlyuc20", "avlyuc30"],
                "sand": [
                    "avlplm10",
                    "avlplm20",
                    "avlplm30",
                    "avlplm40",
                    "avlplm50",
                    "avlyuc10",
                    "avlyuc20",
                    "avlyuc30",
                ],
                "swamp": [
                    "avlswmp0",
                    "avlswmp1",
                    "avlswmp2",
                    "avlswmp3",
                    "avlswmp4",
                    "avlswmp5",
                    "avlswmp6",
                    "avlswmp7",
                    "avltr1d0",
                    "avltr2d0",
                    "avltr3d0",
                    "avlwlw10",
                    "avlwlw20",
                    "avlwlw30",
                ],
            },
            "TREES_2": {
                "rough": [
                    "avltro00",
                    "avltro01",
                    "avltro02",
                    "avltro03",
                    "avltro04",
                    "avltro05",
                    "avltro06",
                    "avltro07",
                    "avltro08",
                    "avltro09",
                    "avltro10",
                    "avltro11",
                    "avltro12",
                    "avltrro0",
                    "avltrro1",
                    "avltrro2",
                    "avltrro3",
                    "avltrro4",
                    "avltrro5",
                    "avltrro6",
                    "avltrro7",
                ],
                "swamp": [
                    "avlswt00",
                    "avlswt01",
                    "avlswt02",
                    "avlswt03",
                    "avlswt04",
                    "avlswt05",
                    "avlswt06",
                    "avlswt07",
                    "avlswt08",
                    "avlswt09",
                    "avlswt10",
                    "avlswt11",
                    "avlswt12",
                    "avlswt13",
                    "avlswt14",
                    "avlswt15",
                    "avlswt16",
                    "avlswt17",
                    "avlswt18",
                    "avlswt19",
                    "avlswtr0",
                    "avlswtr1",
                    "avlswtr2",
                    "avlswtr3",
                    "avlswtr4",
                    "avlswtr5",
                    "avlswtr6",
                    "avlswtr7",
                    "avlswtr8",
                    "avlswtr9",
                ],
            },
            "VOLCANO": {"lava": ["avlvol10", "avlvol20", "avlvol30", "avlvol40", "avlvol50"]},
        }
    },
    "GATE": {
        "QUEST_GATE": {
            "BORDERGUARD": {
                "land": {
                    "lblue": "avxbor00",
                    "green": "avxbor10",
                    "red": "avxbor20",
                    "dblue": "avxbor30",
                    "brown": "avxbor40",
                    "purple": "avxbor50",
                    "white": "avxbor60",
                    "black": "avxbor70",
                }
            },
            "BORDER_GATE": {
                "land": {
                    "lblue": "avxbgt00",
                    "green": "avxbgt10",
                    "red": "avxbgt20",
                    "dblue": "avxbgt30",
                    "brown": "avxbgt40",
                    "purple": "avxbgt50",
                    "white": "avxbgt60",
                    "black": "avxbgt70",
                }
            },
            "QUEST_GUARD": {"land": ["avxbor80"]},
        }
    },
    "QUEST_PAIR": {
        "QUEST_GATE": {
            "KEYMASTER": {
                "land": {
                    "lblue": "avxkey00",
                    "green": "avxkey10",
                    "red": "avxkey20",
                    "dblue": "avxkey30",
                    "brown": "avxkey40",
                    "purple": "avxkey50",
                    "white": "avxkey60",
                    "black": "avxkey70",
                }
            },
            "SEER_HUT": {"land": ["avxseeb0", "avxseer0", "avxseey0"]},
        },
        "TRANSPORT": {
            "MONOLITH_ONE_WAY_ENTRANCE": {
                "land": [
                    "avxmn1b0",
                    "avxmn1r0",
                    "avxmn1y0",
                    "avxmn4i0",
                    "avxmn5i0",
                    "avxmn6i0",
                    "avxmn7i0",
                    "avxmn8i0",
                ]
            },
            "MONOLITH_ONE_WAY_EXIT": {
                "land": [
                    "avxmn4o0",
                    "avxmn5o0",
                    "avxmn6o0",
                    "avxmn7o0",
                    "avxmn8o0",
                    "avxmx1b0",
                    "avxmx1r0",
                    "avxmx1y0",
                ]
            },
            "MONOLITH_TWO_WAY": {
                "land": [
                    "avxmn2g0",
                    "avxmn2o0",
                    "avxmn2p0",
                    "avxmn4b0",
                    "avxmn5b0",
                    "avxmn6b0",
                    "avxmn7b0",
                    "avxmn8b0",
                ]
            },
            "SUBTERRANEAN_GATE": {"land": ["avtcave"]},
            "WHIRLPOOL": {"water": ["avxwhrl0"]},
        },
    },
    "VISIBLE": {
        "BANK": {
            "CREATURE_BANK": {
                "land": [
                    "avxbnk10",
                    "avxbnk20",
                    "avxbnk30",
                    "avxbnk40",
                    "avxbnk50",
                    "avxbnk60",
                    "avxbnk70",
                ]
            },
            "CRYPT": {"land": ["avxgyds0", "avxgyne0", "avxgysn0"]},
            "DERELICT_SHIP": {"water": ["avadlic0"]},
            "DRAGON_UTOPIA": {"land": ["avsutop0"]},
            "PYRAMID": {"land": ["avxprmd0"]},
            "SHIPWRECK": {"water": ["avawre20", "avawrek0"]},
        },
        "BONUS_TEMP": {
            "BUOY": {"water": ["avsbuoy0"]},
            "FAERIE_RING": {"land": ["avsring0"]},
            "FOUNTAIN_OF_FORTUNE": {"land": ["avsfntn0"]},
            "FOUNTAIN_OF_YOUTH": {"land": ["avxfyth0"]},
            "IDOL_OF_FORTUNE": {"land": ["avsidol0"]},
            "MERMAID": {"water": ["avxmerm0"]},
            "OASIS": {"land": ["avxosis0"]},
            "RALLY_FLAG": {"land": ["avxrlly0"]},
            "SIRENS": {"water": ["avxsirn0"]},
            "STABLES": {"land": ["avxstbl0"]},
            "SWAN_POND": {"land": ["avsclvd0", "avsclvg0", "avsclvs0"]},
            "TEMPLE": {"land": ["avstmpl0"]},
            "WATERING_HOLE": {"land": ["avxwtrh0"]},
        },
        "DWELLING": {
            "CREATURE_GENERATOR1": {
                "land": [
                    "avg2ela",
                    "avg2ele",
                    "avg2elf",
                    "avg2elw",
                    "avg2uni",
                    "avgair0",
                    "avgangl0",
                    "avgazur",
                    "avgbasl0",
                    "avgbhld0",
                    "avgbhmt0",
                    "avgbkni0",
                    "avgboar",
                    "avgbone0",
                    "avgcavl0",
                    "avgcdrg",
                    "avgcent0",
                    "avgcros0",
                    "avgcycl0",
                    "avgdemn0",
                    "avgdevl0",
                    "avgdfly0",
                    "avgdwrf0",
                    "avgefre0",
                    "avgelf0",
                    "avgelp",
                    "avgench",
                    "avgerth0",
                    "avgfbrd",
                    "avgfdrg",
                    "avgfire0",
                    "avggarg0",
                    "avggdrg0",
                    "avggeni0",
                    "avggnll0",
                    "avggobl0",
                    "avggogs0",
                    "avggorg0",
                    "avggrem0",
                    "avggrff0",
                    "avghalf",
                    "avgharp0",
                    "avghell0",
                    "avghydr0",
                    "avgimp0",
                    "avglich0",
                    "avglzrd0",
                    "avgmage0",
                    "avgmant0",
                    "avgmdsa0",
                    "avgmino0",
                    "avgmonk0",
                    "avgmumy",
                    "avgnaga0",
                    "avgnomd",
                    "avgogre0",
                    "avgorcg0",
                    "avgpeas",
                    "avgpega0",
                    "avgpike0",
                    "avgpit0",
                    "avgpixie",
                    "avgrdrg0",
                    "avgrocs0",
                    "avgrog",
                    "avgrust",
                    "avgshrp",
                    "avgskel0",
                    "avgswor0",
                    "avgtitn0",
                    "avgtree0",
                    "avgtrll",
                    "avgtrog0",
                    "avgunic0",
                    "avgvamp0",
                    "avgwatr0",
                    "avgwght0",
                    "avgwolf0",
                    "avgwyvn0",
                    "avgzomb0",
                ]
            },
            "CREATURE_GENERATOR4": {"land": ["avgelem0", "avggolm0"]},
            "RANDOM_DWELLING": {"land": ["avrcgen0"]},
            "RANDOM_DWELLING_FACTION": {
                "land": [
                    "avrcgn00",
                    "avrcgn01",
                    "avrcgn02",
                    "avrcgn03",
                    "avrcgn04",
                    "avrcgn05",
                    "avrcgn06",
                    "avrcgn07",
                    "avrcgn08",
                ]
            },
            "RANDOM_DWELLING_LVL": {
                "land": [
                    "avrcgen1",
                    "avrcgen2",
                    "avrcgen3",
                    "avrcgen4",
                    "avrcgen5",
                    "avrcgen6",
                    "avrcgen7",
                ]
            },
            "REFUGEE_CAMP": {"land": ["avgrefg0"]},
            "WAR_MACHINE_FACTORY": {"land": ["avgsieg0"]},
        },
        "GUARD": {
            "MONSTER": {
                "land": [
                    "avwangl",
                    "avwarch",
                    "avwazure",
                    "avwbasl",
                    "avwbehl0",
                    "avwbehx0",
                    "avwbhmt0",
                    "avwbhmx0",
                    "avwbkni0",
                    "avwbknx0",
                    "avwboar",
                    "avwbone0",
                    "avwbonx0",
                    "avwcdrg",
                    "avwcent0",
                    "avwcenx0",
                    "avwcvlr0",
                    "avwcvlx0",
                    "avwcycl0",
                    "avwcycx0",
                    "avwddrx0",
                    "avwdemn0",
                    "avwdemx0",
                    "avwdevl0",
                    "avwdevx0",
                    "avwdfir",
                    "avwdfly",
                    "avwdrag0",
                    "avwdrax0",
                    "avwdwrf0",
                    "avwdwrx0",
                    "avwefre0",
                    "avwefrx0",
                    "avwelfw0",
                    "avwelfx0",
                    "avwelma0",
                    "avwelme0",
                    "avwelmf0",
                    "avwelmw0",
                    "avwench",
                    "avwfbird",
                    "avwfdrg",
                    "avwgarg0",
                    "avwgarx0",
                    "avwgbas",
                    "avwgeni0",
                    "avwgenx0",
                    "avwglmd0",
                    "avwglmg0",
                    "avwgnll0",
                    "avwgnlx0",
                    "avwgobl0",
                    "avwgobx0",
                    "avwgog0",
                    "avwgogx0",
                    "avwgolm0",
                    "avwgolx0",
                    "avwgorg",
                    "avwgorx0",
                    "avwgrem0",
                    "avwgrex0",
                    "avwgrif",
                    "avwgrix0",
                    "avwhalf",
                    "avwharp0",
                    "avwharx0",
                    "avwhcrs",
                    "avwhoun0",
                    "avwhoux0",
                    "avwhydr",
                    "avwhydx0",
                    "avwicee",
                    "avwimp0",
                    "avwimpx0",
                    "avwinfr",
                    "avwlcrs",
                    "avwlich0",
                    "avwlicx0",
                    "avwlizr",
                    "avwlizx0",
                    "avwmage0",
                    "avwmagel",
                    "avwmagx0",
                    "avwmant0",
                    "avwmanx0",
                    "avwmeds",
                    "avwmedx0",
                    "avwmino",
                    "avwminx0",
                    "avwmonk",
                    "avwmonx0",
                    "avwmumy",
                    "avwnaga0",
                    "avwnagx0",
                    "avwnomd",
                    "avwnrg",
                    "avwogre0",
                    "avwogrx0",
                    "avworc0",
                    "avworcx0",
                    "avwpeas",
                    "avwpega0",
                    "avwpegx0",
                    "avwphx",
                    "avwpike",
                    "avwpikx0",
                    "avwpitf0",
                    "avwpitx0",
                    "avwpixie",
                    "avwpsye",
                    "avwrdrg",
                    "avwroc0",
                    "avwrocx0",
                    "avwrog",
                    "avwrust",
                    "avwsharp",
                    "avwskel0",
                    "avwskex0",
                    "avwsprit",
                    "avwstone",
                    "avwstorm",
                    "avwswrd0",
                    "avwswrx0",
                    "avwtitn0",
                    "avwtitx0",
                    "avwtree0",
                    "avwtrex0",
                    "avwtrll",
                    "avwtrog0",
                    "avwunic0",
                    "avwunix0",
                    "avwvamp0",
                    "avwvamx0",
                    "avwwigh",
                    "avwwigx0",
                    "avwwolf0",
                    "avwwolx0",
                    "avwwyvr",
                    "avwwyvx0",
                    "avwzomb0",
                    "avwzomx0",
                ]
            },
            "RANDOM_MONSTER": {"land": ["avwmrnd0"]},
            "RANDOM_MONSTER_L1": {"land": ["avwmon1"]},
            "RANDOM_MONSTER_L2": {"land": ["avwmon2"]},
            "RANDOM_MONSTER_L3": {"land": ["avwmon3"]},
            "RANDOM_MONSTER_L4": {"land": ["avwmon4"]},
            "RANDOM_MONSTER_L5": {"land": ["avwmon5"]},
            "RANDOM_MONSTER_L6": {"land": ["avwmon6"]},
            "RANDOM_MONSTER_L7": {"land": ["avwmon7"]},
        },
        "HERO": {"HERO_PLACEHOLDER": {"land": ["ahplace"]}, "PRISON": {"land": ["avxprsn0"]}},
        "INFO": {
            "CARTOGRAPHER": {
                "dirt": ["avxmaps0"],
                "grass": ["avxmaps0"],
                "lava": ["avxmaps0"],
                "rough": ["avxmaps0"],
                "sand": ["avxmaps0"],
                "snow": ["avxmaps0"],
                "subterr": ["avxmapu0"],
                "swamp": ["avxmaps0"],
                "water": ["avxmapw0"],
            },
            "COVER_OF_DARKNESS": {"land": ["avxcovr0"]},
            "DEN_OF_THIEVES": {"land": ["avxdend0", "avxdent"]},
            "EYE_OF_MAGI": {"land": ["avxeyem0"]},
            "HUT_OF_MAGI": {"land": ["avxhutm0"]},
            "OBELISK": {
                "land": [
                    "avxoblb",
                    "avxoblg",
                    "avxoblk",
                    "avxoblo",
                    "avxoblp",
                    "avxoblw",
                    "avxobly",
                ]
            },
            "OCEAN_BOTTLE": {"water": ["avxbttl0"]},
            "PILLAR_OF_FIRE": {"subterr": ["avxpllr0"]},
            "REDWOOD_OBSERVATORY": {
                "dirt": ["avxredw"],
                "grass": ["avxredw"],
                "lava": ["avxredw"],
                "rough": ["avxredw"],
                "sand": ["avxredw"],
                "snow": ["avxreds0", "avxredw"],
                "swamp": ["avxredw"],
            },
            "SIGN": {
                "dirt": ["avxsndg0"],
                "grass": ["avxsndg0"],
                "lava": ["avxsnlv0"],
                "rough": ["avxsnds0"],
                "sand": ["avxsnds0"],
                "snow": ["avxsnsn0"],
                "subterr": ["avxsndg0"],
                "swamp": ["avxsnsw0"],
            },
        },
        "MANA": {
            "MAGIC_WELL": {
                "dirt": ["avxwelr0"],
                "grass": ["avxwelg0"],
                "lava": ["avxwelr0"],
                "rough": ["avxwelr0"],
                "sand": ["avxwelr0"],
                "snow": ["avxwlsn0"],
                "subterr": ["avxwelr0"],
                "swamp": ["avxwelg0"],
            }
        },
        "MINE": {
            "ABANDONED_MINE": {
                "grass": ["avxamgr"],
                "lava": ["avxamlv"],
                "rough": ["avxamro"],
                "sand": ["avxamds"],
                "snow": ["avxamsn"],
                "subterr": ["avxamsu"],
                "swamp": ["avxamsw"],
            },
            "MAGIC_SPRING": {"rough": ["avxmags0"]},
            "MINE": {
                "dirt": [
                    "avmalch0",
                    "avmcrdr0",
                    "avmgedr0",
                    "avmgodr0",
                    "avmordr0",
                    "avmsawd0",
                    "avmsulf0",
                    "avxabnd0",
                ],
                "grass": [
                    "avmabmg",
                    "avmalch0",
                    "avmcrgr0",
                    "avmcrys0",
                    "avmgems0",
                    "avmgogr0",
                    "avmgold0",
                    "avmore0",
                    "avmsawg0",
                    "avmsulf0",
                ],
                "lava": [
                    "avmalch0",
                    "avmcrvo0",
                    "avmgelv0",
                    "avmgovo0",
                    "avmorlv0",
                    "avmsawl0",
                    "avmsulf0",
                ],
                "rough": [
                    "avmalch0",
                    "avmcrrf0",
                    "avmgerf0",
                    "avmgorf0",
                    "avmorro0",
                    "avmsawr0",
                    "avmsulf0",
                ],
                "sand": [
                    "avmalch0",
                    "avmcrds0",
                    "avmgerf0",
                    "avmgods0",
                    "avmords0",
                    "avmsulf0",
                    "avmswds0",
                ],
                "snow": [
                    "avmalcs0",
                    "avmcrsn0",
                    "avmgesn0",
                    "avmgosn0",
                    "avmorsn0",
                    "avmsulf0",
                    "avmswsn0",
                ],
                "subterr": [
                    "avmalch0",
                    "avmcrsu0",
                    "avmgerf0",
                    "avmgosb0",
                    "avmorsb0",
                    "avmsawl0",
                    "avmsulf0",
                ],
                "swamp": [
                    "avmalch0",
                    "avmcrsw0",
                    "avmgems0",
                    "avmgosw0",
                    "avmorsw0",
                    "avmsawg0",
                    "avmsulf0",
                ],
            },
            "MYSTICAL_GARDEN": {"dirt": ["avtmyst0"], "grass": ["avtmyst0"], "swamp": ["avtmyst0"]},
            "WATER_WHEEL": {
                "dirt": ["avmwwhl0"],
                "grass": ["avmwwhl0"],
                "snow": ["avmwwsn0"],
                "swamp": ["avmwwhl0"],
            },
            "WINDMILL": {"land": ["avmwndd0"], "snow": ["avmwmsn0"]},
        },
        "RESOURCE_PILE": {
            "RANDOM_RESOURCE": {"land": ["avtrndm0"]},
            "RESOURCE": {
                "land": [
                    "avtcrys0",
                    "avtgems0",
                    "avtgold0",
                    "avtmerc0",
                    "avtore0",
                    "avtsulf0",
                    "avtwood0",
                ]
            },
        },
        "REWARD_PICKUP": {
            "ARTIFACT": {
                "land": [
                    "ava0007",
                    "ava0008",
                    "ava0009",
                    "ava0010",
                    "ava0011",
                    "ava0012",
                    "ava0013",
                    "ava0014",
                    "ava0015",
                    "ava0016",
                    "ava0017",
                    "ava0018",
                    "ava0019",
                    "ava0020",
                    "ava0021",
                    "ava0022",
                    "ava0023",
                    "ava0024",
                    "ava0025",
                    "ava0026",
                    "ava0027",
                    "ava0028",
                    "ava0029",
                    "ava0030",
                    "ava0031",
                    "ava0032",
                    "ava0033",
                    "ava0034",
                    "ava0035",
                    "ava0036",
                    "ava0037",
                    "ava0038",
                    "ava0039",
                    "ava0040",
                    "ava0041",
                    "ava0042",
                    "ava0043",
                    "ava0044",
                    "ava0045",
                    "ava0046",
                    "ava0047",
                    "ava0048",
                    "ava0049",
                    "ava0050",
                    "ava0051",
                    "ava0052",
                    "ava0053",
                    "ava0054",
                    "ava0055",
                    "ava0056",
                    "ava0057",
                    "ava0058",
                    "ava0059",
                    "ava0060",
                    "ava0061",
                    "ava0062",
                    "ava0063",
                    "ava0064",
                    "ava0065",
                    "ava0066",
                    "ava0067",
                    "ava0068",
                    "ava0069",
                    "ava0070",
                    "ava0071",
                    "ava0072",
                    "ava0073",
                    "ava0074",
                    "ava0075",
                    "ava0076",
                    "ava0077",
                    "ava0078",
                    "ava0079",
                    "ava0080",
                    "ava0081",
                    "ava0082",
                    "ava0083",
                    "ava0084",
                    "ava0085",
                    "ava0086",
                    "ava0087",
                    "ava0088",
                    "ava0089",
                    "ava0090",
                    "ava0091",
                    "ava0092",
                    "ava0093",
                    "ava0094",
                    "ava0095",
                    "ava0096",
                    "ava0097",
                    "ava0098",
                    "ava0099",
                    "ava0100",
                    "ava0101",
                    "ava0102",
                    "ava0103",
                    "ava0104",
                    "ava0105",
                    "ava0106",
                    "ava0107",
                    "ava0108",
                    "ava0109",
                    "ava0110",
                    "ava0111",
                    "ava0112",
                    "ava0113",
                    "ava0114",
                    "ava0115",
                    "ava0116",
                    "ava0117",
                    "ava0118",
                    "ava0119",
                    "ava0120",
                    "ava0121",
                    "ava0122",
                    "ava0123",
                    "ava0124",
                    "ava0125",
                    "ava0126",
                    "ava0127",
                    "ava0129",
                    "ava0130",
                    "ava0131",
                    "ava0132",
                    "ava0133",
                    "ava0134",
                    "ava0135",
                    "ava0136",
                    "ava0137",
                    "ava0138",
                    "ava0139",
                    "ava0140",
                    "ava0141",
                ]
            },
            "CAMPFIRE": {"land": ["adcfra", "avxcfds0", "avxcflv0", "avxcfsn0"]},
            "CORPSE": {"land": ["avxskds0"]},
            "FLOTSAM": {"water": ["avaflot0"]},
            "LEAN_TO": {"land": ["avmlean0"]},
            "PANDORAS_BOX": {"land": ["ava0128"]},
            "RANDOM_ART": {"land": ["avarand"]},
            "RANDOM_MAJOR_ART": {"land": ["avarnd3"]},
            "RANDOM_MINOR_ART": {"land": ["avarnd2"]},
            "RANDOM_RELIC_ART": {"land": ["avarnd4"]},
            "RANDOM_TREASURE_ART": {"land": ["avarnd1"]},
            "SCHOLAR": {"land": ["avxschl0"]},
            "SEA_CHEST": {"water": ["avxccht0"]},
            "SHIPWRECK_SURVIVOR": {"water": ["avasurv0"]},
            "SPELL_SCROLL": {"land": ["ava0001"]},
            "TREASURE_CHEST": {"land": ["avtchst0"]},
            "WAGON": {"land": ["avtwagn0"]},
            "WARRIORS_TOMB": {"land": ["avxtomb0"]},
        },
        "SPECIAL": {
            "ALTAR_OF_SACRIFICE": {"land": ["avxaltar"]},
            "BLACK_MARKET": {"land": ["avxmktb0"]},
            "EVENT": {"land": ["avzevnt0"]},
            "FREELANCERS_GUILD": {"land": ["avxfgld"]},
            "GARRISON": {"land": ["avcgar10", "avcgar20"]},
            "GARRISON2": {"land": ["avcvgarm", "avcvgr"]},
            "GRAIL": {"land": ["avzgrail"]},
            "SANCTUARY": {"land": ["avxsanc0"]},
            "TAVERN": {"land": ["avxtvrn0"]},
            "TRADING_POST": {"land": ["avxpost0", "avxpstr0"]},
            "TRADING_POST_SNOW": {"land": ["avxpssn"]},
        },
        "SPELL_SKILL": {
            "SHRINE_OF_MAGIC_GESTURE": {"land": ["avxl2sh0"]},
            "SHRINE_OF_MAGIC_INCANTATION": {"land": ["avxl1sh0"]},
            "SHRINE_OF_MAGIC_THOUGHT": {"land": ["avxl3sh0"]},
            "UNIVERSITY": {"land": ["avsuniv0"]},
            "WITCH_HUT": {"land": ["avswtch0"]},
        },
        "STAT_PERMANENT": {
            "ARENA": {"land": ["avsarna0"]},
            "GARDEN_OF_REVELATION": {"land": ["avsgrdn0"]},
            "HILL_FORT": {"land": ["avxhild0", "avxhilg0"]},
            "LEARNING_STONE": {"land": ["avsgzbo0"]},
            "LIBRARY_OF_ENLIGHTENMENT": {"land": ["avslibr0"]},
            "MARLETTO_TOWER": {"land": ["avsmarl"]},
            "MERCENARY_CAMP": {"land": ["avsmerc0"]},
            "SCHOOL_OF_MAGIC": {"land": ["avsschm0"]},
            "SCHOOL_OF_WAR": {"land": ["avswar20"]},
            "STAR_AXIS": {"land": ["avsaxis0"]},
            "TREE_OF_KNOWLEDGE": {"land": ["avxtrek0"]},
        },
        "TERRAIN_MODIFIER": {
            "CLOVER_FIELD": {
                "land": [
                    "avxcf0",
                    "avxcf1",
                    "avxcf2",
                    "avxcf3",
                    "avxcf4",
                    "avxcf5",
                    "avxcf6",
                    "avxcf7",
                ]
            },
            "CURSED_GROUND1": {"land": ["avxcrsd0"]},
            "CURSED_GROUND2": {
                "land": ["avxcg1", "avxcg2", "avxcg3", "avxcg4", "avxcg5", "avxcg6", "avxcg7"]
            },
            "EVIL_FOG": {
                "land": [
                    "avxef0",
                    "avxef1",
                    "avxef2",
                    "avxef3",
                    "avxef4",
                    "avxef5",
                    "avxef6",
                    "avxef7",
                ]
            },
            "FAVORABLE_WINDS": {
                "water": [
                    "avxfw0",
                    "avxfw1",
                    "avxfw2",
                    "avxfw3",
                    "avxfw4",
                    "avxfw5",
                    "avxfw6",
                    "avxfw7",
                ]
            },
            "FIERY_FIELDS": {
                "land": [
                    "avxff0",
                    "avxff1",
                    "avxff2",
                    "avxff3",
                    "avxff4",
                    "avxff5",
                    "avxff6",
                    "avxff7",
                ]
            },
            "HOLY_GROUNDS": {
                "land": [
                    "avxhg0",
                    "avxhg1",
                    "avxhg2",
                    "avxhg3",
                    "avxhg4",
                    "avxhg5",
                    "avxhg6",
                    "avxhg7",
                ]
            },
            "LUCID_POOLS": {
                "land": [
                    "avxlp0",
                    "avxlp1",
                    "avxlp2",
                    "avxlp3",
                    "avxlp4",
                    "avxlp5",
                    "avxlp6",
                    "avxlp7",
                ]
            },
            "MAGIC_CLOUDS": {
                "land": [
                    "avxmc0",
                    "avxmc1",
                    "avxmc2",
                    "avxmc3",
                    "avxmc4",
                    "avxmc5",
                    "avxmc6",
                    "avxmc7",
                ]
            },
            "MAGIC_PLAINS1": {"land": ["avxplns0"]},
            "MAGIC_PLAINS2": {
                "land": ["avxmp1", "avxmp2", "avxmp3", "avxmp4", "avxmp5", "avxmp6", "avxmp7"]
            },
            "ROCKLANDS": {
                "land": [
                    "avxrk0",
                    "avxrk1",
                    "avxrk2",
                    "avxrk3",
                    "avxrk4",
                    "avxrk5",
                    "avxrk6",
                    "avxrk7",
                ]
            },
        },
        "TOWN": {
            "RANDOM_TOWN": {"land": ["avcranx0"]},
            "TOWN": {
                "land": {
                    "castle": "avccasx0",
                    "rampart": "avcramx0",
                    "tower": "avctowx0",
                    "inferno": "avcinfx0",
                    "necropolis": "avcnecx0",
                    "dungeon": "avcdunx0",
                    "stronghold": "avcstrx0",
                    "fortress": "avcftrx0",
                    "conflux": "avchforx",
                }
            },
        },
        "WATER_TRANSPORT": {
            "BOAT": {"water": ["avxboat0", "avxboat1", "avxboat2"]},
            "LIGHTHOUSE": {
                "dirt": ["avxlths0"],
                "grass": ["avxlths0"],
                "lava": ["avxlths0"],
                "rough": ["avxlths0"],
                "sand": ["avxlths0"],
                "snow": ["avxlths0"],
                "swamp": ["avxlths0"],
            },
            "SHIPYARD": {"land": ["avxshyd0"]},
        },
    },
}
# === END GENERATED TAXONOMY ===

# Per-animation placement metadata (footprint mask + class/subclass) so the ontology is
# self-sufficient for tile placement and `.vmap` writing — no corpus needed. Keyed by the
# (lowercase) animation DEF; mask is the B/A/V row-strings (kit.objects.mask_cells semantics),
# decoded from the authoritative objects.txt passability/triggers bitfields. Regenerate with
# `python -m vcmi_mapgen.ontology --regen`.
# === BEGIN GENERATED LEAF_META ===
LEAF_META: dict[str, LeafMeta] = {
    "adcfra": LeafMeta(12, 0, ("A",)),
    "ahplace": LeafMeta(214, 0, ("VVV", "VAV")),
    "ava0001": LeafMeta(93, 0, ("VA",)),
    "ava0007": LeafMeta(5, 7, ("VA",)),
    "ava0008": LeafMeta(5, 8, ("VA",)),
    "ava0009": LeafMeta(5, 9, ("VA",)),
    "ava0010": LeafMeta(5, 10, ("VA",)),
    "ava0011": LeafMeta(5, 11, ("VA",)),
    "ava0012": LeafMeta(5, 12, ("VA",)),
    "ava0013": LeafMeta(5, 13, ("VA",)),
    "ava0014": LeafMeta(5, 14, ("VA",)),
    "ava0015": LeafMeta(5, 15, ("VA",)),
    "ava0016": LeafMeta(5, 16, ("VA",)),
    "ava0017": LeafMeta(5, 17, ("VA",)),
    "ava0018": LeafMeta(5, 18, ("VA",)),
    "ava0019": LeafMeta(5, 19, ("VA",)),
    "ava0020": LeafMeta(5, 20, ("VA",)),
    "ava0021": LeafMeta(5, 21, ("VA",)),
    "ava0022": LeafMeta(5, 22, ("VA",)),
    "ava0023": LeafMeta(5, 23, ("VA",)),
    "ava0024": LeafMeta(5, 24, ("VA",)),
    "ava0025": LeafMeta(5, 25, ("VA",)),
    "ava0026": LeafMeta(5, 26, ("VA",)),
    "ava0027": LeafMeta(5, 27, ("VA",)),
    "ava0028": LeafMeta(5, 28, ("VA",)),
    "ava0029": LeafMeta(5, 29, ("VA",)),
    "ava0030": LeafMeta(5, 30, ("VA",)),
    "ava0031": LeafMeta(5, 31, ("VA",)),
    "ava0032": LeafMeta(5, 32, ("VA",)),
    "ava0033": LeafMeta(5, 33, ("VA",)),
    "ava0034": LeafMeta(5, 34, ("VA",)),
    "ava0035": LeafMeta(5, 35, ("VA",)),
    "ava0036": LeafMeta(5, 36, ("VA",)),
    "ava0037": LeafMeta(5, 37, ("VA",)),
    "ava0038": LeafMeta(5, 38, ("VA",)),
    "ava0039": LeafMeta(5, 39, ("VA",)),
    "ava0040": LeafMeta(5, 40, ("VA",)),
    "ava0041": LeafMeta(5, 41, ("VA",)),
    "ava0042": LeafMeta(5, 42, ("VA",)),
    "ava0043": LeafMeta(5, 43, ("VA",)),
    "ava0044": LeafMeta(5, 44, ("VA",)),
    "ava0045": LeafMeta(5, 45, ("VA",)),
    "ava0046": LeafMeta(5, 46, ("VA",)),
    "ava0047": LeafMeta(5, 47, ("VA",)),
    "ava0048": LeafMeta(5, 48, ("VA",)),
    "ava0049": LeafMeta(5, 49, ("VA",)),
    "ava0050": LeafMeta(5, 50, ("VA",)),
    "ava0051": LeafMeta(5, 51, ("VA",)),
    "ava0052": LeafMeta(5, 52, ("VA",)),
    "ava0053": LeafMeta(5, 53, ("VA",)),
    "ava0054": LeafMeta(5, 54, ("VA",)),
    "ava0055": LeafMeta(5, 55, ("VA",)),
    "ava0056": LeafMeta(5, 56, ("VA",)),
    "ava0057": LeafMeta(5, 57, ("VA",)),
    "ava0058": LeafMeta(5, 58, ("VA",)),
    "ava0059": LeafMeta(5, 59, ("VA",)),
    "ava0060": LeafMeta(5, 60, ("VA",)),
    "ava0061": LeafMeta(5, 61, ("VA",)),
    "ava0062": LeafMeta(5, 62, ("VA",)),
    "ava0063": LeafMeta(5, 63, ("VA",)),
    "ava0064": LeafMeta(5, 64, ("VA",)),
    "ava0065": LeafMeta(5, 65, ("VA",)),
    "ava0066": LeafMeta(5, 66, ("VA",)),
    "ava0067": LeafMeta(5, 67, ("VA",)),
    "ava0068": LeafMeta(5, 68, ("VA",)),
    "ava0069": LeafMeta(5, 69, ("VA",)),
    "ava0070": LeafMeta(5, 70, ("VA",)),
    "ava0071": LeafMeta(5, 71, ("VA",)),
    "ava0072": LeafMeta(5, 72, ("VA",)),
    "ava0073": LeafMeta(5, 73, ("VA",)),
    "ava0074": LeafMeta(5, 74, ("VA",)),
    "ava0075": LeafMeta(5, 75, ("VA",)),
    "ava0076": LeafMeta(5, 76, ("VA",)),
    "ava0077": LeafMeta(5, 77, ("VA",)),
    "ava0078": LeafMeta(5, 78, ("VA",)),
    "ava0079": LeafMeta(5, 79, ("VA",)),
    "ava0080": LeafMeta(5, 80, ("VA",)),
    "ava0081": LeafMeta(5, 81, ("VA",)),
    "ava0082": LeafMeta(5, 82, ("VA",)),
    "ava0083": LeafMeta(5, 83, ("VA",)),
    "ava0084": LeafMeta(5, 84, ("VA",)),
    "ava0085": LeafMeta(5, 85, ("VA",)),
    "ava0086": LeafMeta(5, 86, ("VA",)),
    "ava0087": LeafMeta(5, 87, ("VA",)),
    "ava0088": LeafMeta(5, 88, ("VA",)),
    "ava0089": LeafMeta(5, 89, ("VA",)),
    "ava0090": LeafMeta(5, 90, ("VA",)),
    "ava0091": LeafMeta(5, 91, ("VA",)),
    "ava0092": LeafMeta(5, 92, ("VA",)),
    "ava0093": LeafMeta(5, 93, ("VA",)),
    "ava0094": LeafMeta(5, 94, ("VA",)),
    "ava0095": LeafMeta(5, 95, ("VA",)),
    "ava0096": LeafMeta(5, 96, ("VA",)),
    "ava0097": LeafMeta(5, 97, ("VA",)),
    "ava0098": LeafMeta(5, 98, ("VA",)),
    "ava0099": LeafMeta(5, 99, ("VA",)),
    "ava0100": LeafMeta(5, 100, ("VA",)),
    "ava0101": LeafMeta(5, 101, ("VA",)),
    "ava0102": LeafMeta(5, 102, ("VA",)),
    "ava0103": LeafMeta(5, 103, ("VA",)),
    "ava0104": LeafMeta(5, 104, ("VA",)),
    "ava0105": LeafMeta(5, 105, ("VA",)),
    "ava0106": LeafMeta(5, 106, ("VA",)),
    "ava0107": LeafMeta(5, 107, ("VA",)),
    "ava0108": LeafMeta(5, 108, ("VA",)),
    "ava0109": LeafMeta(5, 109, ("VA",)),
    "ava0110": LeafMeta(5, 110, ("VA",)),
    "ava0111": LeafMeta(5, 111, ("VA",)),
    "ava0112": LeafMeta(5, 112, ("VA",)),
    "ava0113": LeafMeta(5, 113, ("VA",)),
    "ava0114": LeafMeta(5, 114, ("VA",)),
    "ava0115": LeafMeta(5, 115, ("VA",)),
    "ava0116": LeafMeta(5, 116, ("VA",)),
    "ava0117": LeafMeta(5, 117, ("VA",)),
    "ava0118": LeafMeta(5, 118, ("VA",)),
    "ava0119": LeafMeta(5, 119, ("VA",)),
    "ava0120": LeafMeta(5, 120, ("VA",)),
    "ava0121": LeafMeta(5, 121, ("VA",)),
    "ava0122": LeafMeta(5, 122, ("VA",)),
    "ava0123": LeafMeta(5, 123, ("VA",)),
    "ava0124": LeafMeta(5, 124, ("VA",)),
    "ava0125": LeafMeta(5, 125, ("VA",)),
    "ava0126": LeafMeta(5, 126, ("VA",)),
    "ava0127": LeafMeta(5, 127, ("VA",)),
    "ava0128": LeafMeta(6, 0, ("VA",)),
    "ava0129": LeafMeta(5, 128, ("VA",)),
    "ava0130": LeafMeta(5, 129, ("VA",)),
    "ava0131": LeafMeta(5, 130, ("VA",)),
    "ava0132": LeafMeta(5, 131, ("VA",)),
    "ava0133": LeafMeta(5, 132, ("VA",)),
    "ava0134": LeafMeta(5, 133, ("VA",)),
    "ava0135": LeafMeta(5, 134, ("VA",)),
    "ava0136": LeafMeta(5, 135, ("VA",)),
    "ava0137": LeafMeta(5, 136, ("VA",)),
    "ava0138": LeafMeta(5, 137, ("VA",)),
    "ava0139": LeafMeta(5, 138, ("VA",)),
    "ava0140": LeafMeta(5, 139, ("VA",)),
    "ava0141": LeafMeta(5, 140, ("VA",)),
    "avadlic0": LeafMeta(24, 0, ("VVV", "VVV", "VXB")),
    "avaflot0": LeafMeta(29, 0, ("VV", "VA")),
    "avarand": LeafMeta(65, 0, ("VA",)),
    "avarnd1": LeafMeta(66, 0, ("VA",)),
    "avarnd2": LeafMeta(67, 0, ("VA",)),
    "avarnd3": LeafMeta(68, 0, ("VA",)),
    "avarnd4": LeafMeta(69, 0, ("VA",)),
    "avasurv0": LeafMeta(86, 0, ("A",)),
    "avawre20": LeafMeta(85, 0, ("VVV", "VBX")),
    "avawrek0": LeafMeta(85, 0, ("VV", "XB")),
    "avccasx0": LeafMeta(98, 0, ("VVVVVV", "VVVVVV", "VVVVVV", "VVBBBV", "VBBBBB", "VBBXBB")),
    "avcdunx0": LeafMeta(98, 5, ("VVVVVV", "VVVVVV", "VVVVVV", "VVBBBV", "VBBBBB", "VBBXBB")),
    "avcftrx0": LeafMeta(98, 7, ("VVVVVV", "VVVVVV", "VVVVVV", "VVBBBV", "VBBBBB", "VBBXBB")),
    "avcgar10": LeafMeta(33, 0, ("VVVV", "VBXB")),
    "avcgar20": LeafMeta(33, 1, ("VVVV", "VBXB")),
    "avchforx": LeafMeta(98, 8, ("VVVVVV", "VVVVVV", "VVVVVV", "VVBBBV", "VBBBBB", "VBBXBB")),
    "avcinfx0": LeafMeta(98, 3, ("VVVVVV", "VVVVVV", "VVVVVV", "VVBBBV", "VBBBBB", "VBBXBB")),
    "avcnecx0": LeafMeta(98, 4, ("VVVVVV", "VVVVVV", "VVVVVV", "VVBBBV", "VBBBBB", "VBBXBB")),
    "avcramx0": LeafMeta(98, 1, ("VVVVVV", "VVVVVV", "VVVVVV", "VVBBBV", "VBBBBB", "VBBXBB")),
    "avcranx0": LeafMeta(77, 0, ("VVVVVV", "VVVVVV", "VVVVVV", "VVBBBV", "VBBBBB", "VBBXBB")),
    "avcstrx0": LeafMeta(98, 6, ("VVVVVV", "VVVVVV", "VVVVVV", "VVBBBV", "VBBBBB", "VBBXBB")),
    "avctowx0": LeafMeta(98, 2, ("VVVVVV", "VVVVVV", "VVVVVV", "VVBBBV", "VBBBBB", "VBBXBB")),
    "avcvgarm": LeafMeta(219, 1, ("VV", "VB", "VX", "VB")),
    "avcvgr": LeafMeta(219, 0, ("VV", "VB", "VX", "VB")),
    "avg2ela": LeafMeta(17, 69, ("VVV", "VVV", "VBX")),
    "avg2ele": LeafMeta(17, 70, ("VVV", "VVV", "VBX")),
    "avg2elf": LeafMeta(17, 71, ("VVV", "VVV", "VBX")),
    "avg2elw": LeafMeta(17, 72, ("VVV", "VVV", "VBX")),
    "avg2uni": LeafMeta(17, 68, ("VVV", "VVV", "VBX")),
    "avgair0": LeafMeta(17, 7, ("VVV", "BXB")),
    "avgangl0": LeafMeta(17, 8, ("VVVV", "VBXV")),
    "avgazur": LeafMeta(17, 62, ("VVV", "VVV", "VBX")),
    "avgbasl0": LeafMeta(17, 0, ("VV", "BX")),
    "avgbhld0": LeafMeta(17, 2, ("VVV", "VVV", "VXB")),
    "avgbhmt0": LeafMeta(17, 1, ("VVV", "VVV", "VBX")),
    "avgbkni0": LeafMeta(17, 3, ("VVVV", "VVVV", "VVVV", "VVBX")),
    "avgboar": LeafMeta(17, 75, ("VBB", "VBX")),
    "avgbone0": LeafMeta(17, 4, ("VVV", "VVV", "VVV", "VXB")),
    "avgcavl0": LeafMeta(17, 5, ("VVV", "VVV", "VBX")),
    "avgcdrg": LeafMeta(17, 63, ("VVV", "VVV", "VBX")),
    "avgcent0": LeafMeta(17, 6, ("VVV", "VBX")),
    "avgcros0": LeafMeta(17, 57, ("VVV", "VVV", "VXB")),
    "avgcycl0": LeafMeta(17, 9, ("VVV", "VVV", "VBX")),
    "avgdemn0": LeafMeta(17, 37, ("VVV", "VVV", "VBX")),
    "avgdevl0": LeafMeta(17, 10, ("VVV", "VVV", "VBX")),
    "avgdfly0": LeafMeta(17, 11, ("VVV", "VVV", "VBX")),
    "avgdwrf0": LeafMeta(17, 12, ("VVV", "VVV", "VXB")),
    "avgefre0": LeafMeta(17, 14, ("VV", "VV", "XB")),
    "avgelem0": LeafMeta(20, 0, ("VVVV", "VBBB", "VBXB")),
    "avgelf0": LeafMeta(17, 15, ("VVV", "VVV", "VXB")),
    "avgelp": LeafMeta(17, 60, ("VVV", "VVV", "VBX")),
    "avgench": LeafMeta(17, 66, ("VVV", "VVV", "VBX")),
    "avgerth0": LeafMeta(17, 13, ("VVVV", "VVVV", "VBXB")),
    "avgfbrd": LeafMeta(17, 61, ("VVV", "VVV", "VBX")),
    "avgfdrg": LeafMeta(17, 64, ("VVV", "VVV", "VBX")),
    "avgfire0": LeafMeta(17, 16, ("VVVV", "VBXB")),
    "avggarg0": LeafMeta(17, 17, ("VVV", "VVV", "VVV", "VBX")),
    "avggdrg0": LeafMeta(17, 24, ("VVV", "VVV", "VVV", "VBX")),
    "avggeni0": LeafMeta(17, 18, ("VVV", "VVV", "VVV", "VVV", "VBX")),
    "avggnll0": LeafMeta(17, 20, ("VVV", "VBX")),
    "avggobl0": LeafMeta(17, 21, ("VVV", "VVV", "VBX")),
    "avggogs0": LeafMeta(17, 22, ("VVV", "VXB")),
    "avggolm0": LeafMeta(20, 1, ("VVV", "VVV", "VVV", "VBX")),
    "avggorg0": LeafMeta(17, 23, ("VVV", "VVV", "VBX")),
    "avggrem0": LeafMeta(17, 43, ("VVV", "VVV", "VBX")),
    "avggrff0": LeafMeta(17, 25, ("VVV", "VVV", "VBX")),
    "avghalf": LeafMeta(17, 73, ("VVV", "VVV", "VBX")),
    "avgharp0": LeafMeta(17, 26, ("VVV", "VVV", "VBX")),
    "avghell0": LeafMeta(17, 27, ("VV", "BX")),
    "avghydr0": LeafMeta(17, 28, ("VVV", "VXB")),
    "avgimp0": LeafMeta(17, 29, ("VVV", "VVV", "VBX")),
    "avglich0": LeafMeta(17, 52, ("VVV", "VVV", "VBX")),
    "avglzrd0": LeafMeta(17, 30, ("VVV", "VVV", "VBX")),
    "avgmage0": LeafMeta(17, 31, ("VVV", "VVV", "VVV", "VVV", "VBX")),
    "avgmant0": LeafMeta(17, 32, ("VV", "BX")),
    "avgmdsa0": LeafMeta(17, 33, ("VVV", "VVV", "VBX")),
    "avgmino0": LeafMeta(17, 34, ("VVV", "VXB")),
    "avgmonk0": LeafMeta(17, 35, ("VVV", "VVV", "VBX")),
    "avgmumy": LeafMeta(17, 76, ("VVV", "VBB", "VXB")),
    "avgnaga0": LeafMeta(17, 36, ("VVVV", "VVVV", "VVBB", "VVBX")),
    "avgnomd": LeafMeta(17, 77, ("VVV", "VVV", "VBX")),
    "avgogre0": LeafMeta(17, 38, ("VVV", "VVV", "VBB", "VBX")),
    "avgorcg0": LeafMeta(17, 39, ("VVV", "VVV", "VVV", "VBX")),
    "avgpeas": LeafMeta(17, 74, ("VVV", "VVV", "VBX")),
    "avgpega0": LeafMeta(17, 50, ("VVV", "VVV", "VVV", "VBX")),
    "avgpike0": LeafMeta(17, 56, ("VVV", "VBV", "VBX")),
    "avgpit0": LeafMeta(17, 40, ("VVV", "VBX")),
    "avgpixie": LeafMeta(17, 59, ("VVV", "VVV", "VBX")),
    "avgrdrg0": LeafMeta(17, 41, ("VVV", "VXB")),
    "avgrefg0": LeafMeta(78, 0, ("VV", "BX")),
    "avgrocs0": LeafMeta(17, 42, ("VVV", "VVV", "VVV", "VBX")),
    "avgrog": LeafMeta(17, 78, ("VVV", "VVV", "VBX")),
    "avgrust": LeafMeta(17, 65, ("VVV", "VVV", "VBX")),
    "avgshrp": LeafMeta(17, 67, ("VVV", "VVV", "VBX")),
    "avgsieg0": LeafMeta(106, 0, ("VVV", "VXB")),
    "avgskel0": LeafMeta(17, 54, ("VVV", "VBX")),
    "avgswor0": LeafMeta(17, 58, ("VVV", "VVV", "VBX")),
    "avgtitn0": LeafMeta(17, 44, ("VVV", "VBV", "VBX")),
    "avgtree0": LeafMeta(17, 45, ("VVV", "VVV", "VBX")),
    "avgtrll": LeafMeta(17, 79, ("VVV", "VBV", "VBX")),
    "avgtrog0": LeafMeta(17, 46, ("VVV", "VVV", "VBX")),
    "avgunic0": LeafMeta(17, 51, ("VVVV", "VBBV", "VBXB")),
    "avgvamp0": LeafMeta(17, 53, ("VVV", "VXB")),
    "avgwatr0": LeafMeta(17, 47, ("VVVV", "VVBV", "VBXB")),
    "avgwght0": LeafMeta(17, 48, ("VVVV", "VVVV", "VVVV", "VVXB")),
    "avgwolf0": LeafMeta(17, 19, ("VVV", "VBV", "VBX")),
    "avgwyvn0": LeafMeta(17, 49, ("VVV", "VVV", "VXB")),
    "avgzomb0": LeafMeta(17, 55, ("VVV", "VBX")),
    "avlautr0": LeafMeta(135, 0, ("VV", "VB")),
    "avlautr1": LeafMeta(135, 0, ("VV", "VB")),
    "avlautr2": LeafMeta(135, 0, ("VVVV", "VVBB", "VBBV")),
    "avlautr3": LeafMeta(135, 0, ("VVVV", "VVBB", "VBBV")),
    "avlautr4": LeafMeta(135, 0, ("VVVV", "VBBV", "VVBB")),
    "avlautr5": LeafMeta(135, 0, ("VVVV", "VBBV", "VVBB")),
    "avlautr6": LeafMeta(135, 0, ("VVVV", "VBBV", "VBBB", "VVBB")),
    "avlautr7": LeafMeta(135, 0, ("VVVV", "VVBB", "VBBB", "VBBV")),
    "avlbuzr0": LeafMeta(147, 0, ("VV", "BB")),
    "avlc10l0": LeafMeta(118, 0, ("BB",)),
    "avlc11l0": LeafMeta(118, 0, ("BB", "VB")),
    "avlc12l0": LeafMeta(118, 0, ("B",)),
    "avlc13l0": LeafMeta(118, 0, ("B",)),
    "avlc14l0": LeafMeta(118, 0, ("B",)),
    "avlca010": LeafMeta(116, 0, ("B",)),
    "avlca020": LeafMeta(116, 0, ("B",)),
    "avlca030": LeafMeta(116, 0, ("B",)),
    "avlca040": LeafMeta(116, 0, ("B",)),
    "avlca050": LeafMeta(116, 0, ("B",)),
    "avlca060": LeafMeta(116, 0, ("V", "B")),
    "avlca070": LeafMeta(116, 0, ("B",)),
    "avlca080": LeafMeta(116, 0, ("B",)),
    "avlca090": LeafMeta(116, 0, ("V", "B")),
    "avlca100": LeafMeta(116, 0, ("V", "B")),
    "avlca110": LeafMeta(116, 0, ("B",)),
    "avlca120": LeafMeta(116, 0, ("B",)),
    "avlca130": LeafMeta(116, 0, ("B",)),
    "avlca1r0": LeafMeta(116, 0, ("V", "B")),
    "avlca2r0": LeafMeta(116, 0, ("B",)),
    "avlct1d0": LeafMeta(118, 0, ("BB",)),
    "avlct1g0": LeafMeta(118, 0, ("BBBB", "VBBB")),
    "avlct1l0": LeafMeta(118, 0, ("BBBB", "BBBB")),
    "avlct1r0": LeafMeta(118, 0, ("VBB", "BBV")),
    "avlct1u0": LeafMeta(118, 0, ("BB",)),
    "avlct2d0": LeafMeta(118, 0, ("BB",)),
    "avlct2g0": LeafMeta(118, 0, ("BBB", "BBB", "BBB")),
    "avlct2l0": LeafMeta(118, 0, ("BB", "BB", "BB", "BB")),
    "avlct2r0": LeafMeta(118, 0, ("BB", "BB", "BV")),
    "avlct2u0": LeafMeta(118, 0, ("B",)),
    "avlct3d0": LeafMeta(118, 0, ("BB",)),
    "avlct3g0": LeafMeta(118, 0, ("BB", "BB")),
    "avlct3l0": LeafMeta(118, 0, ("BB", "BB")),
    "avlct3r0": LeafMeta(118, 0, ("BBB",)),
    "avlct3u0": LeafMeta(118, 0, ("B", "B")),
    "avlct4d0": LeafMeta(118, 0, ("BB",)),
    "avlct4g0": LeafMeta(118, 0, ("B",)),
    "avlct4l0": LeafMeta(118, 0, ("BB", "BV")),
    "avlct4r0": LeafMeta(118, 0, ("BB",)),
    "avlct4u0": LeafMeta(118, 0, ("BB", "BB")),
    "avlct5d0": LeafMeta(118, 0, ("BB", "BB")),
    "avlct5g0": LeafMeta(118, 0, ("BB",)),
    "avlct5l0": LeafMeta(118, 0, ("B", "B")),
    "avlct5r0": LeafMeta(118, 0, ("BB",)),
    "avlct5u0": LeafMeta(118, 0, ("B",)),
    "avlct6g0": LeafMeta(118, 0, ("B",)),
    "avlct6l0": LeafMeta(118, 0, ("B", "B")),
    "avlct6r0": LeafMeta(118, 0, ("BB", "BB")),
    "avlct7l0": LeafMeta(118, 0, ("B", "B")),
    "avlct7r0": LeafMeta(118, 0, ("B",)),
    "avlct8l0": LeafMeta(118, 0, ("B", "B")),
    "avlct8r0": LeafMeta(118, 0, ("BB",)),
    "avlct9l0": LeafMeta(118, 0, ("BB",)),
    "avlct9r0": LeafMeta(118, 0, ("BB", "BB")),
    "avlctds0": LeafMeta(118, 0, ("BB",)),
    "avlctrd0": LeafMeta(118, 0, ("BB",)),
    "avlctrg0": LeafMeta(118, 0, ("BB",)),
    "avlctrl0": LeafMeta(118, 0, ("BB",)),
    "avlctrr0": LeafMeta(118, 0, ("BB",)),
    "avlctrs0": LeafMeta(118, 0, ("BB",)),
    "avlctsn0": LeafMeta(118, 0, ("BB",)),
    "avld1sn0": LeafMeta(119, 0, ("VVV", "VBB")),
    "avld2sn0": LeafMeta(119, 0, ("VVVV", "VBBB")),
    "avld3sn0": LeafMeta(119, 0, ("VV", "VB")),
    "avld4sn0": LeafMeta(119, 0, ("VVV", "VBB")),
    "avld5sn0": LeafMeta(119, 0, ("VV", "VB")),
    "avld6sn0": LeafMeta(119, 0, ("VV", "VB")),
    "avld7sn0": LeafMeta(119, 0, ("VV", "VB")),
    "avld8sn0": LeafMeta(119, 0, ("VV", "VB")),
    "avld9sn0": LeafMeta(119, 0, ("VV", "VB")),
    "avlddsn0": LeafMeta(119, 0, ("VV", "VB")),
    "avlddsn1": LeafMeta(119, 0, ("VV", "VB")),
    "avlddsn2": LeafMeta(119, 0, ("VVVV", "VBBV", "VVBB")),
    "avlddsn3": LeafMeta(119, 0, ("VVVV", "VVBB", "VBBV")),
    "avlddsn4": LeafMeta(119, 0, ("VVVV", "VBBV", "VVBB")),
    "avlddsn5": LeafMeta(119, 0, ("VVVV", "VVBB", "VBBV")),
    "avlddsn6": LeafMeta(119, 0, ("VVVV", "VBBV", "VBBB", "VVBB")),
    "avlddsn7": LeafMeta(119, 0, ("VVVV", "VVBB", "VBBB", "VBBV")),
    "avldead0": LeafMeta(119, 0, ("VV", "VB")),
    "avldead1": LeafMeta(119, 0, ("VV", "VB")),
    "avldead2": LeafMeta(119, 0, ("VVVV", "VBBV", "VVBB")),
    "avldead3": LeafMeta(119, 0, ("VVVV", "VVBB", "VBBV")),
    "avldead4": LeafMeta(119, 0, ("VVVV", "VBBV", "VVBB")),
    "avldead5": LeafMeta(119, 0, ("VVVV", "VVBB", "VBBV")),
    "avldead6": LeafMeta(119, 0, ("VVVV", "VBBV", "VBBB", "VVBB")),
    "avldead7": LeafMeta(119, 0, ("VVVV", "VVBB", "VBBB", "VBBV")),
    "avldlog": LeafMeta(130, 0, ("B",)),
    "avldt1s0": LeafMeta(119, 0, ("VV", "VV", "BB")),
    "avldt2s0": LeafMeta(119, 0, ("VV", "BB")),
    "avldt3s0": LeafMeta(119, 0, ("BB", "BB")),
    "avldun10": LeafMeta(148, 0, ("BB",)),
    "avldun20": LeafMeta(148, 0, ("BB",)),
    "avldun30": LeafMeta(148, 0, ("BBB",)),
    "avlf01g0": LeafMeta(120, 0, ("B",)),
    "avlf02g0": LeafMeta(120, 0, ("VBBB",)),
    "avlf03g0": LeafMeta(120, 0, ("VVV", "BBB")),
    "avlf04g0": LeafMeta(120, 0, ("VBBB",)),
    "avlf05g0": LeafMeta(120, 0, ("VBBB",)),
    "avlf06g0": LeafMeta(120, 0, ("VVV", "VBB")),
    "avlf07g0": LeafMeta(120, 0, ("BB",)),
    "avlf08g0": LeafMeta(120, 0, ("VBB",)),
    "avlf09g0": LeafMeta(120, 0, ("VB",)),
    "avlf10g0": LeafMeta(120, 0, ("BB",)),
    "avlf11g0": LeafMeta(120, 0, ("VB",)),
    "avlf12g0": LeafMeta(120, 0, ("B",)),
    "avlfl1d0": LeafMeta(120, 0, ("VBB",)),
    "avlfl2d0": LeafMeta(120, 0, ("VBB",)),
    "avlfl3d0": LeafMeta(120, 0, ("VBB",)),
    "avlfl4d0": LeafMeta(120, 0, ("VBB",)),
    "avlfl5d0": LeafMeta(120, 0, ("BBB",)),
    "avlfl6d0": LeafMeta(120, 0, ("B",)),
    "avlfl7d0": LeafMeta(120, 0, ("BB",)),
    "avlfl8d0": LeafMeta(120, 0, ("BB",)),
    "avlfl9d0": LeafMeta(120, 0, ("B",)),
    "avlflk10": LeafMeta(121, 0, ("BBBBB", "BBBBB")),
    "avlflk20": LeafMeta(121, 0, ("BBB",)),
    "avlflk30": LeafMeta(121, 0, ("BB",)),
    "avlglly0": LeafMeta(117, 0, ("BBVV", "BBBB", "VVBB")),
    "avlhlds0": LeafMeta(124, 0, ("B",)),
    "avlhlsn0": LeafMeta(124, 0, ("B",)),
    "avlhold0": LeafMeta(124, 0, ("B",)),
    "avlholg0": LeafMeta(124, 0, ("B",)),
    "avlholl0": LeafMeta(124, 0, ("B",)),
    "avlholr0": LeafMeta(124, 0, ("B",)),
    "avlhols0": LeafMeta(124, 0, ("B",)),
    "avlholx0": LeafMeta(124, 0, ("B",)),
    "avlklp10": LeafMeta(125, 0, ("B",)),
    "avlklp20": LeafMeta(125, 0, ("B",)),
    "avllav10": LeafMeta(128, 0, ("BB", "BB")),
    "avllav20": LeafMeta(127, 0, ("VBB", "BBB")),
    "avllav30": LeafMeta(127, 0, ("BBBBBB", "BBBBBB")),
    "avllav40": LeafMeta(127, 0, ("BBB", "BBB")),
    "avllav50": LeafMeta(127, 0, ("BBB", "BBB")),
    "avllav60": LeafMeta(127, 0, ("BB", "BB")),
    "avllav70": LeafMeta(127, 0, ("BB", "BB")),
    "avllav80": LeafMeta(127, 0, ("BB", "BB")),
    "avllav90": LeafMeta(127, 0, ("BBB", "BBB")),
    "avllk1d0": LeafMeta(126, 0, ("BBBBBBB", "BBBBBBB", "BBBVVVV")),
    "avllk1g0": LeafMeta(126, 0, ("BBBBB", "BBBBB", "VBBBV")),
    "avllk1r": LeafMeta(177, 0, ("VBBV", "BBBB")),
    "avllk1s0": LeafMeta(126, 0, ("VBBBBBV", "VBBBBBV", "VVBBBBV")),
    "avllk1u0": LeafMeta(126, 0, ("VVBBBBBB", "VBBBBBBB", "VBBBBBBV")),
    "avllk2d0": LeafMeta(126, 0, ("BBBB", "BBBB")),
    "avllk2g0": LeafMeta(126, 0, ("BBBB", "BBBB")),
    "avllk2s0": LeafMeta(126, 0, ("VBBB", "VBBV")),
    "avllk2u0": LeafMeta(126, 0, ("VVVV", "BBBB", "BBBB")),
    "avllk3d0": LeafMeta(126, 0, ("BB",)),
    "avllk3g0": LeafMeta(126, 0, ("BBB",)),
    "avllk3s0": LeafMeta(126, 0, ("BBV", "BBV", "BBV")),
    "avllk3u0": LeafMeta(126, 0, ("VV", "BB")),
    "avlllk10": LeafMeta(128, 0, ("BBB", "BBB")),
    "avlllk20": LeafMeta(128, 0, ("BB", "BB")),
    "avllv100": LeafMeta(127, 0, ("BBB", "BBB")),
    "avllv110": LeafMeta(127, 0, ("BB", "BB")),
    "avllv120": LeafMeta(127, 0, ("BB",)),
    "avllv130": LeafMeta(127, 0, ("BB",)),
    "avllv140": LeafMeta(127, 0, ("BB",)),
    "avllv150": LeafMeta(127, 0, ("B",)),
    "avllv160": LeafMeta(127, 0, ("B",)),
    "avllv170": LeafMeta(127, 0, ("B",)),
    "avllv180": LeafMeta(127, 0, ("BB", "BB")),
    "avllv190": LeafMeta(127, 0, ("BB", "BB")),
    "avllv1u0": LeafMeta(127, 0, ("BB", "BB")),
    "avllv200": LeafMeta(127, 0, ("BB", "BB")),
    "avllv210": LeafMeta(127, 0, ("B",)),
    "avllv220": LeafMeta(127, 0, ("B",)),
    "avllv230": LeafMeta(127, 0, ("B", "B")),
    "avllv240": LeafMeta(127, 0, ("BB",)),
    "avllv250": LeafMeta(127, 0, ("B", "B")),
    "avllv260": LeafMeta(127, 0, ("BB",)),
    "avllv2u0": LeafMeta(127, 0, ("B", "B")),
    "avllv3u0": LeafMeta(127, 0, ("BB",)),
    "avlman10": LeafMeta(131, 0, ("B",)),
    "avlman20": LeafMeta(131, 0, ("BB",)),
    "avlman30": LeafMeta(131, 0, ("B",)),
    "avlman40": LeafMeta(131, 0, ("BBB",)),
    "avlman50": LeafMeta(131, 0, ("B",)),
    "avlmd1d0": LeafMeta(133, 0, ("BB",)),
    "avlmd1g0": LeafMeta(133, 0, ("BB",)),
    "avlmd1r0": LeafMeta(133, 0, ("BB",)),
    "avlmd2d0": LeafMeta(133, 0, ("BB",)),
    "avlmd2g0": LeafMeta(133, 0, ("BB",)),
    "avlmd2r0": LeafMeta(133, 0, ("VB",)),
    "avlmd3r0": LeafMeta(133, 0, ("BB",)),
    "avlmoss0": LeafMeta(132, 0, ("B",)),
    "avlms010": LeafMeta(129, 0, ("BB",)),
    "avlms020": LeafMeta(129, 0, ("B",)),
    "avlms030": LeafMeta(129, 0, ("B",)),
    "avlms040": LeafMeta(129, 0, ("B",)),
    "avlms050": LeafMeta(129, 0, ("B",)),
    "avlms060": LeafMeta(129, 0, ("BB",)),
    "avlms070": LeafMeta(129, 0, ("VV", "BB")),
    "avlms080": LeafMeta(129, 0, ("B",)),
    "avlms090": LeafMeta(129, 0, ("B",)),
    "avlms100": LeafMeta(129, 0, ("VB",)),
    "avlms110": LeafMeta(129, 0, ("B",)),
    "avlms120": LeafMeta(129, 0, ("VV", "BB")),
    "avlmtdr1": LeafMeta(134, 0, ("VVVVVV", "VBBBBV", "VBBBBB", "VVVBBB")),
    "avlmtdr2": LeafMeta(134, 0, ("VVVVVV", "VVBBBB", "VBBBBB", "VBBBVV")),
    "avlmtdr3": LeafMeta(134, 0, ("VVVV", "VBBB", "VVBB")),
    "avlmtdr4": LeafMeta(134, 0, ("VVVV", "VBBB", "VBBV")),
    "avlmtdr5": LeafMeta(134, 0, ("VBBV", "VVBB")),
    "avlmtdr6": LeafMeta(134, 0, ("VVBB", "VBBV")),
    "avlmtdr7": LeafMeta(134, 0, ("VVVVVV", "VBBBVV", "VVVBBB")),
    "avlmtdr8": LeafMeta(134, 0, ("VVVVVV", "VVVBBB", "VBBBVV")),
    "avlmtds1": LeafMeta(134, 0, ("VVVVVV", "VBBBBV", "VBBBBB", "VVVBBB")),
    "avlmtds2": LeafMeta(134, 0, ("VVVVVV", "VVBBBB", "VBBBBB", "VBBBVV")),
    "avlmtds3": LeafMeta(134, 0, ("VVVV", "VBBB", "VVBB")),
    "avlmtds4": LeafMeta(134, 0, ("VVVV", "VBBB", "VBBV")),
    "avlmtds5": LeafMeta(134, 0, ("VBBV", "VVBB")),
    "avlmtds6": LeafMeta(134, 0, ("VVBB", "VBBV")),
    "avlmtgn0": LeafMeta(134, 0, ("VVVVVV", "VVBBBB", "VBBBBB", "VBBBVV")),
    "avlmtgn1": LeafMeta(134, 0, ("VVVVVV", "VBBBBV", "VBBBBB", "VVVBBB")),
    "avlmtgn2": LeafMeta(134, 0, ("VVVV", "VBBB", "VBBV")),
    "avlmtgn3": LeafMeta(134, 0, ("VVVV", "VBBB", "VVBB")),
    "avlmtgn4": LeafMeta(134, 0, ("VVBB", "VBBV")),
    "avlmtgn5": LeafMeta(134, 0, ("VBBV", "VVBB")),
    "avlmtgr1": LeafMeta(134, 0, ("VVVVVV", "VVVVVV", "VBBBBV", "VBBBBB", "VVVBBB")),
    "avlmtgr2": LeafMeta(134, 0, ("VVVVVV", "VVBBBB", "VBBBBB", "VBBBVV")),
    "avlmtgr3": LeafMeta(134, 0, ("VVVV", "VBBB", "VVBB")),
    "avlmtgr4": LeafMeta(134, 0, ("VVVV", "VBBB", "VBBV")),
    "avlmtgr5": LeafMeta(134, 0, ("BBV", "VBB")),
    "avlmtgr6": LeafMeta(134, 0, ("VBB", "BBV")),
    "avlmtrf1": LeafMeta(134, 0, ("VVVVVV", "VBBBBV", "VBBBBB", "VVVBBB")),
    "avlmtrf2": LeafMeta(134, 0, ("VVVVVV", "VVBBBB", "VBBBBB", "VBBBVV")),
    "avlmtrf3": LeafMeta(134, 0, ("VVVV", "VBBB", "VVBB")),
    "avlmtrf4": LeafMeta(134, 0, ("VVVV", "VBBB", "VBBV")),
    "avlmtrf5": LeafMeta(134, 0, ("VBBV", "VVBB")),
    "avlmtrf6": LeafMeta(134, 0, ("VVBB", "VBBV")),
    "avlmtsb0": LeafMeta(134, 0, ("VVVVVV", "VVBBBB", "VBBBBB", "VBBBVV")),
    "avlmtsb1": LeafMeta(134, 0, ("VVVVVV", "VBBBBV", "VBBBBB", "VVVBBB")),
    "avlmtsb2": LeafMeta(134, 0, ("VVVV", "VBBB", "VBBV")),
    "avlmtsb3": LeafMeta(134, 0, ("VVVV", "VBBB", "VVBB")),
    "avlmtsb4": LeafMeta(134, 0, ("VVVV", "VVBB", "VBBV")),
    "avlmtsb5": LeafMeta(134, 0, ("VVVV", "VBBV", "VVBB")),
    "avlmtsn1": LeafMeta(134, 0, ("VVVVV", "BBBBV", "BBBBB", "VVBBB")),
    "avlmtsn2": LeafMeta(134, 0, ("VVVVVV", "VVBBBB", "VBBBBB", "VBBBVV")),
    "avlmtsn3": LeafMeta(134, 0, ("VVVV", "VBBB", "VVBB")),
    "avlmtsn4": LeafMeta(134, 0, ("VVVV", "VBBB", "VBBV")),
    "avlmtsn5": LeafMeta(134, 0, ("VVVV", "VBBV", "VVBB")),
    "avlmtsn6": LeafMeta(134, 0, ("VVBB", "VBBV")),
    "avlmtsw1": LeafMeta(134, 0, ("VVVVVV", "VBBBBV", "VBBBBB", "VVVBBB")),
    "avlmtsw2": LeafMeta(134, 0, ("VVVVVV", "VVBBBB", "VBBBBB", "VBBBVV")),
    "avlmtsw3": LeafMeta(134, 0, ("VVVV", "VBBB", "VVBB")),
    "avlmtsw4": LeafMeta(134, 0, ("VVVV", "VBBB", "VBBV")),
    "avlmtsw5": LeafMeta(134, 0, ("VBBV", "VVBB")),
    "avlmtsw6": LeafMeta(134, 0, ("VVVV", "VVBB", "VBBV")),
    "avlmtvo1": LeafMeta(134, 0, ("VVVVV", "BBBBV", "BBBBB", "VVBBB")),
    "avlmtvo2": LeafMeta(134, 0, ("VVVVV", "VBBBV", "BBBBB", "BBBVV")),
    "avlmtvo3": LeafMeta(134, 0, ("VVV", "BBB", "VBB")),
    "avlmtvo4": LeafMeta(134, 0, ("VVV", "BBB", "BBV")),
    "avlmtvo5": LeafMeta(134, 0, ("BBV", "VBB")),
    "avlmtvo6": LeafMeta(134, 0, ("VBB", "BBV")),
    "avlo1sn0": LeafMeta(136, 0, ("BB",)),
    "avlo2sn0": LeafMeta(136, 0, ("BB",)),
    "avlo3sn0": LeafMeta(136, 0, ("BBB",)),
    "avloc1d0": LeafMeta(136, 0, ("BB",)),
    "avloc1g0": LeafMeta(136, 0, ("BB",)),
    "avloc1r0": LeafMeta(136, 0, ("BB",)),
    "avloc1u0": LeafMeta(136, 0, ("BB",)),
    "avloc2d0": LeafMeta(136, 0, ("BB",)),
    "avloc2g0": LeafMeta(136, 0, ("BB",)),
    "avloc2r0": LeafMeta(136, 0, ("BB",)),
    "avloc2u0": LeafMeta(136, 0, ("BB",)),
    "avloc3d0": LeafMeta(136, 0, ("BB",)),
    "avloc3g0": LeafMeta(136, 0, ("BB",)),
    "avloc3r0": LeafMeta(136, 0, ("BB",)),
    "avloc3u0": LeafMeta(136, 0, ("BB",)),
    "avloc4r0": LeafMeta(136, 0, ("BB",)),
    "avloc4u0": LeafMeta(136, 0, ("BB",)),
    "avlp1sn0": LeafMeta(153, 0, ("B",)),
    "avlp2sn0": LeafMeta(153, 0, ("B",)),
    "avlplm10": LeafMeta(155, 0, ("B",)),
    "avlplm20": LeafMeta(155, 0, ("VV", "VB")),
    "avlplm30": LeafMeta(155, 0, ("VV", "VB")),
    "avlplm40": LeafMeta(155, 0, ("VV", "VB")),
    "avlplm50": LeafMeta(155, 0, ("VVV", "VBV")),
    "avlpntr0": LeafMeta(137, 0, ("VV", "VB")),
    "avlpntr1": LeafMeta(137, 0, ("VV", "VB")),
    "avlpntr2": LeafMeta(137, 0, ("VVVV", "VVBB", "VBBV")),
    "avlpntr3": LeafMeta(137, 0, ("VVVV", "VVBB", "VBBV")),
    "avlpntr4": LeafMeta(137, 0, ("VVVV", "VBBV", "VVBB")),
    "avlpntr5": LeafMeta(137, 0, ("VVVV", "VBBV", "VVBB")),
    "avlpntr6": LeafMeta(137, 0, ("VVVV", "VBBV", "VBBB", "VVBB")),
    "avlpntr7": LeafMeta(137, 0, ("VVVV", "VVBB", "VBBB", "VBBV")),
    "avlr01u0": LeafMeta(147, 0, ("VVV", "VBB")),
    "avlr02r0": LeafMeta(147, 0, ("VV", "BB")),
    "avlr02u0": LeafMeta(147, 0, ("VV", "BB")),
    "avlr03r0": LeafMeta(147, 0, ("BB",)),
    "avlr03u0": LeafMeta(147, 0, ("VBB",)),
    "avlr04r0": LeafMeta(147, 0, ("VV", "BB")),
    "avlr04u0": LeafMeta(147, 0, ("BB",)),
    "avlr05u0": LeafMeta(147, 0, ("BB",)),
    "avlr06r0": LeafMeta(147, 0, ("BB",)),
    "avlr06u0": LeafMeta(147, 0, ("VV", "VB")),
    "avlr07r0": LeafMeta(147, 0, ("BB",)),
    "avlr07u0": LeafMeta(147, 0, ("V", "B")),
    "avlr08r0": LeafMeta(147, 0, ("BB",)),
    "avlr08u0": LeafMeta(147, 0, ("VB",)),
    "avlr09r0": LeafMeta(147, 0, ("VV", "BB")),
    "avlr09u0": LeafMeta(147, 0, ("B",)),
    "avlr10r0": LeafMeta(147, 0, ("V", "B")),
    "avlr10u0": LeafMeta(147, 0, ("VBB",)),
    "avlr11r0": LeafMeta(147, 0, ("V", "B")),
    "avlr11u0": LeafMeta(147, 0, ("V", "B")),
    "avlr12r0": LeafMeta(147, 0, ("V", "B")),
    "avlr12u0": LeafMeta(147, 0, ("VV", "BB")),
    "avlr13r0": LeafMeta(147, 0, ("V", "B")),
    "avlr13u0": LeafMeta(147, 0, ("B",)),
    "avlr14r0": LeafMeta(147, 0, ("B",)),
    "avlr14u0": LeafMeta(147, 0, ("B",)),
    "avlr15r0": LeafMeta(147, 0, ("B",)),
    "avlr15u0": LeafMeta(147, 0, ("VB",)),
    "avlr16u0": LeafMeta(147, 0, ("B",)),
    "avlr1sn0": LeafMeta(147, 0, ("B",)),
    "avlr2sn0": LeafMeta(147, 0, ("VV", "BB")),
    "avlr3sn0": LeafMeta(147, 0, ("B",)),
    "avlr4sn0": LeafMeta(147, 0, ("B",)),
    "avlr5sn0": LeafMeta(147, 0, ("B",)),
    "avlr6sn0": LeafMeta(147, 0, ("BB",)),
    "avlr7sn0": LeafMeta(147, 0, ("B",)),
    "avlr8sn0": LeafMeta(147, 0, ("B",)),
    "avlrd01": LeafMeta(147, 0, ("BB",)),
    "avlrd02": LeafMeta(147, 0, ("VVV", "VBB")),
    "avlrd04": LeafMeta(147, 0, ("VB",)),
    "avlref10": LeafMeta(161, 0, ("VBB", "BBB", "BBV")),
    "avlref20": LeafMeta(161, 0, ("BBV", "BBB", "VBB")),
    "avlref30": LeafMeta(161, 0, ("BB", "BB")),
    "avlref40": LeafMeta(161, 0, ("VB", "BB")),
    "avlref50": LeafMeta(161, 0, ("BB",)),
    "avlref60": LeafMeta(161, 0, ("B", "B")),
    "avlrg01": LeafMeta(147, 0, ("BB",)),
    "avlrg02": LeafMeta(147, 0, ("BB",)),
    "avlrg03": LeafMeta(147, 0, ("VB",)),
    "avlrg04": LeafMeta(147, 0, ("VB",)),
    "avlrg05": LeafMeta(147, 0, ("VB",)),
    "avlrg06": LeafMeta(147, 0, ("VB",)),
    "avlrg07": LeafMeta(147, 0, ("VB",)),
    "avlrg08": LeafMeta(147, 0, ("VB",)),
    "avlrg09": LeafMeta(147, 0, ("VB",)),
    "avlrg10": LeafMeta(147, 0, ("VB",)),
    "avlrg11": LeafMeta(147, 0, ("B",)),
    "avlrk1s0": LeafMeta(147, 0, ("B",)),
    "avlrk1w0": LeafMeta(147, 0, ("VV", "BB")),
    "avlrk2s0": LeafMeta(147, 0, ("B",)),
    "avlrk2w0": LeafMeta(147, 0, ("V", "B")),
    "avlrk3d0": LeafMeta(147, 0, ("BB",)),
    "avlrk3s0": LeafMeta(147, 0, ("VV", "BB")),
    "avlrk3w0": LeafMeta(147, 0, ("B",)),
    "avlrk4s0": LeafMeta(147, 0, ("B",)),
    "avlrk4w0": LeafMeta(147, 0, ("B",)),
    "avlrk5d0": LeafMeta(147, 0, ("B",)),
    "avlroug0": LeafMeta(155, 0, ("VV", "VB")),
    "avlroug1": LeafMeta(155, 0, ("VV", "VB")),
    "avlroug2": LeafMeta(155, 0, ("VV", "VB")),
    "avlrr01": LeafMeta(147, 0, ("B",)),
    "avlrr05": LeafMeta(147, 0, ("BB",)),
    "avls01s0": LeafMeta(150, 0, ("BB",)),
    "avls02s0": LeafMeta(150, 0, ("BBB",)),
    "avls03s0": LeafMeta(150, 0, ("BBBBB",)),
    "avls04s0": LeafMeta(150, 0, ("BBB",)),
    "avls05s0": LeafMeta(150, 0, ("B",)),
    "avls06s0": LeafMeta(150, 0, ("VV", "BB")),
    "avls07s0": LeafMeta(150, 0, ("B",)),
    "avls08s0": LeafMeta(150, 0, ("B",)),
    "avls09s0": LeafMeta(150, 0, ("BB",)),
    "avls10s0": LeafMeta(150, 0, ("B",)),
    "avls11s0": LeafMeta(150, 0, ("B",)),
    "avls1sn0": LeafMeta(150, 0, ("B",)),
    "avls2sn0": LeafMeta(150, 0, ("B",)),
    "avls3sn0": LeafMeta(150, 0, ("BB",)),
    "avlsh1d0": LeafMeta(150, 0, ("BB",)),
    "avlsh1g0": LeafMeta(150, 0, ("VBBB",)),
    "avlsh1r0": LeafMeta(150, 0, ("B",)),
    "avlsh2d0": LeafMeta(150, 0, ("BB",)),
    "avlsh2g0": LeafMeta(150, 0, ("BBB",)),
    "avlsh2r0": LeafMeta(150, 0, ("B",)),
    "avlsh3d0": LeafMeta(150, 0, ("BB",)),
    "avlsh3g0": LeafMeta(150, 0, ("VBB",)),
    "avlsh3r0": LeafMeta(150, 0, ("B",)),
    "avlsh4d0": LeafMeta(150, 0, ("BB",)),
    "avlsh4g0": LeafMeta(150, 0, ("VBB",)),
    "avlsh4r0": LeafMeta(150, 0, ("B",)),
    "avlsh5d0": LeafMeta(150, 0, ("B",)),
    "avlsh5g0": LeafMeta(150, 0, ("VBB",)),
    "avlsh5r0": LeafMeta(150, 0, ("B",)),
    "avlsh6d0": LeafMeta(150, 0, ("BBB",)),
    "avlsh6g0": LeafMeta(150, 0, ("BB",)),
    "avlsh6r0": LeafMeta(150, 0, ("BB",)),
    "avlsh7d0": LeafMeta(150, 0, ("BB",)),
    "avlsh7r0": LeafMeta(150, 0, ("B",)),
    "avlsh8d0": LeafMeta(150, 0, ("B",)),
    "avlsh8r0": LeafMeta(150, 0, ("B",)),
    "avlsh9r0": LeafMeta(150, 0, ("BB",)),
    "avlskul0": LeafMeta(151, 0, ("B",)),
    "avlsntr0": LeafMeta(137, 0, ("VV", "VB")),
    "avlsntr1": LeafMeta(137, 0, ("VV", "VB")),
    "avlsntr2": LeafMeta(137, 0, ("VVVV", "VVBB", "VBBV")),
    "avlsntr3": LeafMeta(137, 0, ("VVVV", "VVBB", "VBBV")),
    "avlsntr4": LeafMeta(137, 0, ("VVVV", "VBBV", "VVBB")),
    "avlsntr5": LeafMeta(137, 0, ("VVVV", "VBBV", "VVBB")),
    "avlsntr6": LeafMeta(137, 0, ("VVVV", "VVBB", "VBBB", "VBBV")),
    "avlsntr7": LeafMeta(137, 0, ("VVVV", "VBBV", "VBBB", "VVBB")),
    "avlspit0": LeafMeta(149, 0, ("BBB",)),
    "avlsptr0": LeafMeta(135, 0, ("VV", "VB")),
    "avlsptr1": LeafMeta(135, 0, ("VV", "VB")),
    "avlsptr2": LeafMeta(135, 0, ("VV", "VB")),
    "avlsptr3": LeafMeta(135, 0, ("VVVV", "VVBB", "VBBV")),
    "avlsptr4": LeafMeta(135, 0, ("VVVV", "VVBB", "VBBV")),
    "avlsptr5": LeafMeta(135, 0, ("VVVV", "VBBV", "VVBB")),
    "avlsptr6": LeafMeta(135, 0, ("VVVV", "VBBV", "VVBB")),
    "avlsptr7": LeafMeta(135, 0, ("VVVV", "VBBV", "VBBB", "VVBB")),
    "avlsptr8": LeafMeta(135, 0, ("VVVV", "VVBB", "VBBB", "VBBV")),
    "avlstg10": LeafMeta(147, 0, ("BB",)),
    "avlstg20": LeafMeta(147, 0, ("B",)),
    "avlstg30": LeafMeta(147, 0, ("B",)),
    "avlstg40": LeafMeta(147, 0, ("B",)),
    "avlstg50": LeafMeta(147, 0, ("B",)),
    "avlstg60": LeafMeta(147, 0, ("VV", "VB")),
    "avlstm1": LeafMeta(153, 0, ("B",)),
    "avlstm2": LeafMeta(153, 0, ("B",)),
    "avlstm3": LeafMeta(153, 0, ("VB",)),
    "avlswmp0": LeafMeta(155, 0, ("VV", "VB")),
    "avlswmp1": LeafMeta(155, 0, ("VV", "VB")),
    "avlswmp2": LeafMeta(155, 0, ("VVVV", "VBBV", "VVBB")),
    "avlswmp3": LeafMeta(155, 0, ("VVVV", "VVBB", "VBBV")),
    "avlswmp4": LeafMeta(155, 0, ("VVVV", "VBBV", "VVBB")),
    "avlswmp5": LeafMeta(155, 0, ("VVVV", "VVBB", "VBBV")),
    "avlswmp6": LeafMeta(155, 0, ("VVVV", "VBBV", "VBBB", "VVBB")),
    "avlswmp7": LeafMeta(155, 0, ("VVVV", "VVBB", "VBBB", "VBBV")),
    "avlswp10": LeafMeta(150, 0, ("VBBBB", "BBBBB")),
    "avlswp20": LeafMeta(150, 0, ("BBB",)),
    "avlswp30": LeafMeta(150, 0, ("BBB",)),
    "avlswp40": LeafMeta(150, 0, ("BB",)),
    "avlswp50": LeafMeta(126, 0, ("BB",)),
    "avlswp60": LeafMeta(119, 0, ("BB",)),
    "avlswp70": LeafMeta(119, 0, ("B",)),
    "avlswt00": LeafMeta(199, 0, ("V", "B")),
    "avlswt01": LeafMeta(199, 0, ("V", "B")),
    "avlswt02": LeafMeta(199, 0, ("V", "B")),
    "avlswt03": LeafMeta(199, 0, ("V", "B")),
    "avlswt04": LeafMeta(199, 0, ("V", "B")),
    "avlswt05": LeafMeta(199, 0, ("V", "B")),
    "avlswt06": LeafMeta(199, 0, ("VV", "VB")),
    "avlswt07": LeafMeta(199, 0, ("VV", "VB")),
    "avlswt08": LeafMeta(199, 0, ("B",)),
    "avlswt09": LeafMeta(199, 0, ("B",)),
    "avlswt10": LeafMeta(199, 0, ("VB",)),
    "avlswt11": LeafMeta(199, 0, ("V", "B")),
    "avlswt12": LeafMeta(199, 0, ("VV", "VB")),
    "avlswt13": LeafMeta(199, 0, ("VV", "VB")),
    "avlswt14": LeafMeta(199, 0, ("VV", "VB")),
    "avlswt15": LeafMeta(199, 0, ("B",)),
    "avlswt16": LeafMeta(199, 0, ("B",)),
    "avlswt17": LeafMeta(199, 0, ("VV", "VB")),
    "avlswt18": LeafMeta(199, 0, ("B",)),
    "avlswt19": LeafMeta(199, 0, ("VV", "VB")),
    "avlswtr0": LeafMeta(199, 0, ("VVVV", "VBBV", "VVBB")),
    "avlswtr1": LeafMeta(199, 0, ("VVVV", "VVBB", "VBBV")),
    "avlswtr2": LeafMeta(199, 0, ("VVVV", "VBBV", "VVBB")),
    "avlswtr3": LeafMeta(199, 0, ("VVVV", "VVBB", "VBBV")),
    "avlswtr4": LeafMeta(199, 0, ("VVVV", "VBBV", "VBBB", "VVBV")),
    "avlswtr5": LeafMeta(199, 0, ("VVBBVV", "VBBVBV")),
    "avlswtr6": LeafMeta(199, 0, ("VBV", "VBV")),
    "avlswtr7": LeafMeta(199, 0, ("VVBV", "VBBB")),
    "avlswtr8": LeafMeta(199, 0, ("VBB", "VBB")),
    "avlswtr9": LeafMeta(199, 0, ("VVVVVV", "VBBVBB", "VVBBBV")),
    "avltr1d0": LeafMeta(155, 0, ("VVV", "VBV")),
    "avltr2d0": LeafMeta(155, 0, ("VVV", "VBV")),
    "avltr3d0": LeafMeta(155, 0, ("VV", "VB")),
    "avltro00": LeafMeta(199, 0, ("VB",)),
    "avltro01": LeafMeta(199, 0, ("VV", "VB")),
    "avltro02": LeafMeta(199, 0, ("VB",)),
    "avltro03": LeafMeta(199, 0, ("VB",)),
    "avltro04": LeafMeta(199, 0, ("B",)),
    "avltro05": LeafMeta(199, 0, ("VB",)),
    "avltro06": LeafMeta(199, 0, ("B",)),
    "avltro07": LeafMeta(199, 0, ("VV", "VB")),
    "avltro08": LeafMeta(199, 0, ("VV", "VB")),
    "avltro09": LeafMeta(199, 0, ("VV", "VB")),
    "avltro10": LeafMeta(199, 0, ("VB",)),
    "avltro11": LeafMeta(199, 0, ("VV", "VB")),
    "avltro12": LeafMeta(199, 0, ("VB",)),
    "avltrro0": LeafMeta(199, 0, ("VVVV", "VBBV", "VVBB")),
    "avltrro1": LeafMeta(199, 0, ("VVVV", "VVBB", "VBBV")),
    "avltrro2": LeafMeta(199, 0, ("VVVV", "VBBV", "VVBB")),
    "avltrro3": LeafMeta(199, 0, ("VVVV", "VVBB", "VBBV")),
    "avltrro4": LeafMeta(199, 0, ("VVVV", "VBBV", "VVBB")),
    "avltrro5": LeafMeta(199, 0, ("VVVV", "VVBB", "VBBV")),
    "avltrro6": LeafMeta(199, 0, ("VV", "VB")),
    "avltrro7": LeafMeta(199, 0, ("VV", "VB")),
    "avlvol10": LeafMeta(158, 0, ("VV", "BB")),
    "avlvol20": LeafMeta(158, 0, ("VV", "BB")),
    "avlvol30": LeafMeta(158, 0, ("VVV", "VVV", "BBB")),
    "avlvol40": LeafMeta(158, 0, ("VBV", "BBB")),
    "avlvol50": LeafMeta(158, 0, ("VVVVV", "VVVVV", "VVVVV", "VBBBV", "VBBBV")),
    "avlwlw10": LeafMeta(155, 0, ("VVV", "BBB")),
    "avlwlw20": LeafMeta(155, 0, ("VV", "BB")),
    "avlwlw30": LeafMeta(155, 0, ("V", "B")),
    "avlxds01": LeafMeta(206, 0, ("BB", "BB")),
    "avlxds02": LeafMeta(206, 0, ("BB", "BB")),
    "avlxds03": LeafMeta(206, 0, ("VV", "BB")),
    "avlxds04": LeafMeta(206, 0, ("BB", "BB")),
    "avlxds05": LeafMeta(206, 0, ("BV", "BB")),
    "avlxds06": LeafMeta(206, 0, ("BB", "BB")),
    "avlxds07": LeafMeta(206, 0, ("BBB",)),
    "avlxds08": LeafMeta(206, 0, ("BBB",)),
    "avlxds09": LeafMeta(206, 0, ("BBB",)),
    "avlxds10": LeafMeta(206, 0, ("B",)),
    "avlxds11": LeafMeta(206, 0, ("B",)),
    "avlxds12": LeafMeta(206, 0, ("B",)),
    "avlxdt00": LeafMeta(207, 0, ("VV", "BB")),
    "avlxdt01": LeafMeta(207, 0, ("VV", "BB")),
    "avlxdt02": LeafMeta(207, 0, ("VV", "BB")),
    "avlxdt03": LeafMeta(207, 0, ("VV", "BB")),
    "avlxdt04": LeafMeta(207, 0, ("VV", "BB")),
    "avlxdt05": LeafMeta(207, 0, ("VV", "BB")),
    "avlxdt06": LeafMeta(207, 0, ("VVV", "BBB")),
    "avlxdt07": LeafMeta(207, 0, ("VVV", "BBB")),
    "avlxdt08": LeafMeta(207, 0, ("VVV", "BBB")),
    "avlxdt09": LeafMeta(207, 0, ("VVV", "BBB")),
    "avlxdt10": LeafMeta(207, 0, ("VVV", "BBB")),
    "avlxdt11": LeafMeta(207, 0, ("VVV", "BBB")),
    "avlxgr01": LeafMeta(208, 0, ("VV", "BB")),
    "avlxgr02": LeafMeta(208, 0, ("VV", "BB")),
    "avlxgr03": LeafMeta(208, 0, ("VV", "BB")),
    "avlxgr04": LeafMeta(208, 0, ("BB", "BB")),
    "avlxgr05": LeafMeta(208, 0, ("VV", "BB")),
    "avlxgr06": LeafMeta(208, 0, ("BB", "BB")),
    "avlxgr07": LeafMeta(208, 0, ("BBB",)),
    "avlxgr08": LeafMeta(208, 0, ("BBB",)),
    "avlxgr09": LeafMeta(208, 0, ("BBB",)),
    "avlxgr10": LeafMeta(208, 0, ("B",)),
    "avlxgr11": LeafMeta(208, 0, ("B",)),
    "avlxgr12": LeafMeta(208, 0, ("B",)),
    "avlxro01": LeafMeta(209, 0, ("VV", "BB")),
    "avlxro02": LeafMeta(209, 0, ("BB", "BB")),
    "avlxro03": LeafMeta(209, 0, ("VB", "BB")),
    "avlxro04": LeafMeta(209, 0, ("BB", "BB")),
    "avlxro05": LeafMeta(209, 0, ("VV", "BB")),
    "avlxro06": LeafMeta(209, 0, ("BB", "BB")),
    "avlxro07": LeafMeta(209, 0, ("BBB",)),
    "avlxro08": LeafMeta(209, 0, ("BBB",)),
    "avlxro09": LeafMeta(209, 0, ("BBB",)),
    "avlxro10": LeafMeta(209, 0, ("B",)),
    "avlxro11": LeafMeta(209, 0, ("B",)),
    "avlxro12": LeafMeta(209, 0, ("B",)),
    "avlxsu01": LeafMeta(210, 0, ("BB", "BB")),
    "avlxsu02": LeafMeta(210, 0, ("BB", "BB")),
    "avlxsu03": LeafMeta(210, 0, ("BB", "BB")),
    "avlxsu04": LeafMeta(210, 0, ("BB", "BB")),
    "avlxsu05": LeafMeta(210, 0, ("VV", "BB")),
    "avlxsu06": LeafMeta(210, 0, ("VB", "BB")),
    "avlxsu07": LeafMeta(210, 0, ("BBB",)),
    "avlxsu08": LeafMeta(210, 0, ("BBB",)),
    "avlxsu09": LeafMeta(210, 0, ("BBB",)),
    "avlxsu10": LeafMeta(210, 0, ("B",)),
    "avlxsu11": LeafMeta(210, 0, ("B",)),
    "avlxsu12": LeafMeta(210, 0, ("B",)),
    "avlxsw01": LeafMeta(211, 0, ("BB", "BB")),
    "avlxsw02": LeafMeta(211, 0, ("BB", "BB")),
    "avlxsw03": LeafMeta(211, 0, ("BB", "BB")),
    "avlxsw04": LeafMeta(211, 0, ("BB", "BB")),
    "avlxsw05": LeafMeta(211, 0, ("BB", "BB")),
    "avlxsw06": LeafMeta(211, 0, ("BB", "BB")),
    "avlxsw07": LeafMeta(211, 0, ("BBB",)),
    "avlxsw08": LeafMeta(211, 0, ("BBB",)),
    "avlxsw09": LeafMeta(211, 0, ("BBB",)),
    "avlxsw10": LeafMeta(211, 0, ("B",)),
    "avlxsw11": LeafMeta(211, 0, ("B",)),
    "avlyuc10": LeafMeta(155, 0, ("B",)),
    "avlyuc20": LeafMeta(155, 0, ("B",)),
    "avlyuc30": LeafMeta(155, 0, ("B",)),
    "avmabmg": LeafMeta(53, 7, ("VVV", "BXB")),
    "avmalch0": LeafMeta(53, 1, ("VVV", "VVV", "BXB")),
    "avmalcs0": LeafMeta(53, 1, ("VVV", "VVV", "BXB")),
    "avmcrdr0": LeafMeta(53, 4, ("VVVV", "VBXB")),
    "avmcrds0": LeafMeta(53, 4, ("VVVV", "VBBB", "VBXB")),
    "avmcrgr0": LeafMeta(53, 4, ("VVV", "BXB")),
    "avmcrrf0": LeafMeta(53, 4, ("VVV", "VVV", "BXB")),
    "avmcrsn0": LeafMeta(53, 4, ("VVVV", "VVVV", "VBXB")),
    "avmcrsu0": LeafMeta(53, 4, ("VVVV", "VBXB")),
    "avmcrsw0": LeafMeta(53, 4, ("VVVV", "VBBB", "VBXB")),
    "avmcrvo0": LeafMeta(53, 4, ("VVVV", "VVVV", "VBXB")),
    "avmcrys0": LeafMeta(53, 4, ("VVV", "BXB")),
    "avmgedr0": LeafMeta(53, 5, ("BBB", "BXB")),
    "avmgelv0": LeafMeta(53, 5, ("BBB", "BXB")),
    "avmgems0": LeafMeta(53, 5, ("BBB", "BXB")),
    "avmgerf0": LeafMeta(53, 5, ("BBB", "BXB")),
    "avmgesn0": LeafMeta(53, 5, ("BBB", "BXB")),
    "avmgodr0": LeafMeta(53, 6, ("VVVV", "VBXB")),
    "avmgods0": LeafMeta(53, 6, ("VVVV", "VBBB", "VBXB")),
    "avmgogr0": LeafMeta(53, 6, ("VVV", "BXB")),
    "avmgold0": LeafMeta(53, 6, ("VVV", "BXB")),
    "avmgorf0": LeafMeta(53, 6, ("VVV", "VVV", "BXB")),
    "avmgosb0": LeafMeta(53, 6, ("VVVV", "VBXB")),
    "avmgosn0": LeafMeta(53, 6, ("VVVV", "VVVV", "VBXB")),
    "avmgosw0": LeafMeta(53, 6, ("VVVV", "VBBB", "VBXB")),
    "avmgovo0": LeafMeta(53, 6, ("VVVV", "VVVV", "VBXB")),
    "avmlean0": LeafMeta(39, 0, ("VV", "BX")),
    "avmordr0": LeafMeta(53, 2, ("BBB", "BXB")),
    "avmords0": LeafMeta(53, 2, ("BBB", "BXB")),
    "avmore0": LeafMeta(53, 2, ("BBB", "BXB")),
    "avmorlv0": LeafMeta(53, 2, ("BBB", "BXB")),
    "avmorro0": LeafMeta(53, 2, ("BBB", "BXB")),
    "avmorsb0": LeafMeta(53, 2, ("BBB", "BXB")),
    "avmorsn0": LeafMeta(53, 2, ("BBB", "BXB")),
    "avmorsw0": LeafMeta(53, 2, ("BBB", "BXB")),
    "avmsawd0": LeafMeta(53, 0, ("VVVVV", "VVVBB", "VBBXB")),
    "avmsawg0": LeafMeta(53, 0, ("VVVVV", "VVVBB", "VBBXB")),
    "avmsawl0": LeafMeta(53, 0, ("VVVVV", "VVVBB", "VBBXB")),
    "avmsawr0": LeafMeta(53, 0, ("VVVVV", "VVVBB", "VBBXB")),
    "avmsulf0": LeafMeta(53, 3, ("VVV", "BXB")),
    "avmswds0": LeafMeta(53, 0, ("VVVVV", "VVVBB", "VBBXB")),
    "avmswsn0": LeafMeta(53, 0, ("VVVBB", "VBBXB")),
    "avmwmsn0": LeafMeta(112, 0, ("VVVVV", "VVVVV", "VVVAV")),
    "avmwndd0": LeafMeta(112, 0, ("VVVVV", "VVVVV", "VVVAV")),
    "avmwwhl0": LeafMeta(109, 0, ("VVV", "BBB", "BBX")),
    "avmwwsn0": LeafMeta(109, 0, ("VVV", "VVV", "BBX")),
    "avrcgen0": LeafMeta(216, 0, ("VVV", "VBB", "VXX")),
    "avrcgen1": LeafMeta(217, 0, ("VVV", "VBB", "VXX")),
    "avrcgen2": LeafMeta(217, 1, ("VVV", "VBB", "VXX")),
    "avrcgen3": LeafMeta(217, 2, ("VVV", "VBB", "VXX")),
    "avrcgen4": LeafMeta(217, 3, ("VVV", "VBB", "VXX")),
    "avrcgen5": LeafMeta(217, 4, ("VVV", "VBB", "VXX")),
    "avrcgen6": LeafMeta(217, 5, ("VVV", "VBB", "VXX")),
    "avrcgen7": LeafMeta(217, 6, ("VVV", "VBB", "VXX")),
    "avrcgn00": LeafMeta(218, 0, ("VVV", "VBB", "VXX")),
    "avrcgn01": LeafMeta(218, 1, ("VVV", "VBB", "VXX")),
    "avrcgn02": LeafMeta(218, 2, ("VVV", "VBB", "VXX")),
    "avrcgn03": LeafMeta(218, 3, ("VVV", "VBB", "VXX")),
    "avrcgn04": LeafMeta(218, 4, ("VVV", "VBB", "VXX")),
    "avrcgn05": LeafMeta(218, 5, ("VVV", "VBB", "VXX")),
    "avrcgn06": LeafMeta(218, 6, ("VVV", "VBB", "VXX")),
    "avrcgn07": LeafMeta(218, 7, ("VVV", "VBB", "VXX")),
    "avrcgn08": LeafMeta(218, 8, ("VVV", "VBB", "VXX")),
    "avsarna0": LeafMeta(4, 0, ("VVV", "BBB", "BXB")),
    "avsaxis0": LeafMeta(61, 0, ("VV", "VA")),
    "avsbuoy0": LeafMeta(11, 0, ("A",)),
    "avsclvd0": LeafMeta(14, 0, ("VXB",)),
    "avsclvg0": LeafMeta(14, 0, ("VXB",)),
    "avsclvs0": LeafMeta(14, 0, ("VXB",)),
    "avsfntn0": LeafMeta(30, 0, ("VV", "VA")),
    "avsgrdn0": LeafMeta(32, 0, ("VV", "VA")),
    "avsgzbo0": LeafMeta(100, 0, ("VV", "VA")),
    "avsidol0": LeafMeta(38, 0, ("VV", "VA")),
    "avslibr0": LeafMeta(41, 0, ("VVVBB", "VBBXB")),
    "avsmarl": LeafMeta(23, 0, ("VVV", "VVV", "VBX")),
    "avsmerc0": LeafMeta(51, 0, ("VVV", "BXB")),
    "avsring0": LeafMeta(28, 0, ("VVV", "VXB")),
    "avsschm0": LeafMeta(47, 0, ("VV", "VV", "VA")),
    "avstmpl0": LeafMeta(96, 0, ("VV", "XB")),
    "avsuniv0": LeafMeta(104, 0, ("VBBBV", "VBBBB", "VBBXB")),
    "avsutop0": LeafMeta(25, 0, ("VVVVVVV", "VVVVVVV", "VVVBBBB", "VBBBBBV", "VVVBBXV")),
    "avswar20": LeafMeta(107, 0, ("VVVV", "VBBV", "BBBB", "VBXV")),
    "avswtch0": LeafMeta(113, 0, ("VVV", "VVV", "VAV")),
    "avtcave": LeafMeta(103, 0, ("VVVV", "VVBV", "VBXB")),
    "avtchst0": LeafMeta(101, 0, ("VA",)),
    "avtcrys0": LeafMeta(79, 4, ("VA",)),
    "avtgems0": LeafMeta(79, 5, ("VA",)),
    "avtgold0": LeafMeta(79, 6, ("VA",)),
    "avtmerc0": LeafMeta(79, 1, ("VA",)),
    "avtmyst0": LeafMeta(55, 0, ("VVV", "BXB")),
    "avtore0": LeafMeta(79, 2, ("VA",)),
    "avtrndm0": LeafMeta(76, 0, ("VA",)),
    "avtsulf0": LeafMeta(79, 3, ("VA",)),
    "avtwagn0": LeafMeta(105, 0, ("VA",)),
    "avtwood0": LeafMeta(79, 0, ("VA",)),
    "avwangl": LeafMeta(54, 12, ("VV", "VA")),
    "avwarch": LeafMeta(54, 13, ("VV", "VA")),
    "avwazure": LeafMeta(54, 132, ("VV", "VA")),
    "avwbasl": LeafMeta(54, 106, ("VV", "VA")),
    "avwbehl0": LeafMeta(54, 74, ("VV", "VA")),
    "avwbehx0": LeafMeta(54, 75, ("VV", "VA")),
    "avwbhmt0": LeafMeta(54, 96, ("VV", "VA")),
    "avwbhmx0": LeafMeta(54, 97, ("VV", "VA")),
    "avwbkni0": LeafMeta(54, 66, ("VV", "VA")),
    "avwbknx0": LeafMeta(54, 67, ("VV", "VA")),
    "avwboar": LeafMeta(54, 140, ("VV", "VA")),
    "avwbone0": LeafMeta(54, 68, ("VV", "VA")),
    "avwbonx0": LeafMeta(54, 69, ("VV", "VA")),
    "avwcdrg": LeafMeta(54, 133, ("VV", "VA")),
    "avwcent0": LeafMeta(54, 14, ("VV", "VA")),
    "avwcenx0": LeafMeta(54, 15, ("VV", "VA")),
    "avwcvlr0": LeafMeta(54, 10, ("VV", "VA")),
    "avwcvlx0": LeafMeta(54, 11, ("VV", "VA")),
    "avwcycl0": LeafMeta(54, 94, ("VV", "VA")),
    "avwcycx0": LeafMeta(54, 95, ("VV", "VA")),
    "avwddrx0": LeafMeta(54, 83, ("VV", "VA")),
    "avwdemn0": LeafMeta(54, 48, ("VV", "VA")),
    "avwdemx0": LeafMeta(54, 49, ("VV", "VA")),
    "avwdevl0": LeafMeta(54, 54, ("VV", "VA")),
    "avwdevx0": LeafMeta(54, 55, ("VV", "VA")),
    "avwdfir": LeafMeta(54, 105, ("VV", "VA")),
    "avwdfly": LeafMeta(54, 104, ("VV", "VA")),
    "avwdrag0": LeafMeta(54, 26, ("VV", "VA")),
    "avwdrax0": LeafMeta(54, 27, ("VV", "VA")),
    "avwdwrf0": LeafMeta(54, 16, ("VV", "VA")),
    "avwdwrx0": LeafMeta(54, 17, ("VV", "VA")),
    "avwefre0": LeafMeta(54, 52, ("VV", "VA")),
    "avwefrx0": LeafMeta(54, 53, ("VV", "VA")),
    "avwelfw0": LeafMeta(54, 18, ("VV", "VA")),
    "avwelfx0": LeafMeta(54, 19, ("VV", "VA")),
    "avwelma0": LeafMeta(54, 112, ("VV", "VA")),
    "avwelme0": LeafMeta(54, 113, ("VV", "VA")),
    "avwelmf0": LeafMeta(54, 114, ("VV", "VA")),
    "avwelmw0": LeafMeta(54, 115, ("VV", "VA")),
    "avwench": LeafMeta(54, 136, ("VV", "VA")),
    "avwfbird": LeafMeta(54, 130, ("VV", "VA")),
    "avwfdrg": LeafMeta(54, 134, ("VV", "VA")),
    "avwgarg0": LeafMeta(54, 30, ("VV", "VA")),
    "avwgarx0": LeafMeta(54, 31, ("VV", "VA")),
    "avwgbas": LeafMeta(54, 107, ("VV", "VA")),
    "avwgeni0": LeafMeta(54, 36, ("VV", "VA")),
    "avwgenx0": LeafMeta(54, 37, ("VV", "VA")),
    "avwglmd0": LeafMeta(54, 117, ("VV", "VA")),
    "avwglmg0": LeafMeta(54, 116, ("VV", "VA")),
    "avwgnll0": LeafMeta(54, 98, ("VV", "VA")),
    "avwgnlx0": LeafMeta(54, 99, ("VV", "VA")),
    "avwgobl0": LeafMeta(54, 84, ("VV", "VA")),
    "avwgobx0": LeafMeta(54, 85, ("VV", "VA")),
    "avwgog0": LeafMeta(54, 44, ("VV", "VA")),
    "avwgogx0": LeafMeta(54, 45, ("VV", "VA")),
    "avwgolm0": LeafMeta(54, 32, ("VV", "VA")),
    "avwgolx0": LeafMeta(54, 33, ("VV", "VA")),
    "avwgorg": LeafMeta(54, 102, ("VV", "VA")),
    "avwgorx0": LeafMeta(54, 103, ("VV", "VA")),
    "avwgrem0": LeafMeta(54, 28, ("VV", "VA")),
    "avwgrex0": LeafMeta(54, 29, ("VV", "VA")),
    "avwgrif": LeafMeta(54, 4, ("VV", "VA")),
    "avwgrix0": LeafMeta(54, 5, ("VV", "VA")),
    "avwhalf": LeafMeta(54, 138, ("VV", "VA")),
    "avwharp0": LeafMeta(54, 72, ("VV", "VA")),
    "avwharx0": LeafMeta(54, 73, ("VV", "VA")),
    "avwhcrs": LeafMeta(54, 3, ("VV", "VA")),
    "avwhoun0": LeafMeta(54, 46, ("VV", "VA")),
    "avwhoux0": LeafMeta(54, 47, ("VV", "VA")),
    "avwhydr": LeafMeta(54, 110, ("VV", "VA")),
    "avwhydx0": LeafMeta(54, 111, ("VV", "VA")),
    "avwicee": LeafMeta(54, 123, ("VV", "VA")),
    "avwimp0": LeafMeta(54, 42, ("VV", "VA")),
    "avwimpx0": LeafMeta(54, 43, ("VV", "VA")),
    "avwinfr": LeafMeta(54, 71, ("VV", "VA")),
    "avwlcrs": LeafMeta(54, 2, ("VV", "VA")),
    "avwlich0": LeafMeta(54, 64, ("VV", "VA")),
    "avwlicx0": LeafMeta(54, 65, ("VV", "VA")),
    "avwlizr": LeafMeta(54, 100, ("VV", "VA")),
    "avwlizx0": LeafMeta(54, 101, ("VV", "VA")),
    "avwmage0": LeafMeta(54, 34, ("VV", "VA")),
    "avwmagel": LeafMeta(54, 121, ("VV", "VA")),
    "avwmagx0": LeafMeta(54, 35, ("VV", "VA")),
    "avwmant0": LeafMeta(54, 80, ("VV", "VA")),
    "avwmanx0": LeafMeta(54, 81, ("VV", "VA")),
    "avwmeds": LeafMeta(54, 76, ("VV", "VA")),
    "avwmedx0": LeafMeta(54, 77, ("VV", "VA")),
    "avwmino": LeafMeta(54, 78, ("VV", "VA")),
    "avwminx0": LeafMeta(54, 79, ("VV", "VA")),
    "avwmon1": LeafMeta(72, 0, ("VV", "VA")),
    "avwmon2": LeafMeta(73, 0, ("VV", "VA")),
    "avwmon3": LeafMeta(74, 0, ("VV", "VA")),
    "avwmon4": LeafMeta(75, 0, ("VV", "VA")),
    "avwmon5": LeafMeta(162, 0, ("VV", "VA")),
    "avwmon6": LeafMeta(163, 0, ("VV", "VA")),
    "avwmon7": LeafMeta(164, 0, ("VV", "VA")),
    "avwmonk": LeafMeta(54, 8, ("VV", "VA")),
    "avwmonx0": LeafMeta(54, 9, ("VV", "VA")),
    "avwmrnd0": LeafMeta(71, 0, ("VV", "VA")),
    "avwmumy": LeafMeta(54, 141, ("VV", "VA")),
    "avwnaga0": LeafMeta(54, 38, ("VV", "VA")),
    "avwnagx0": LeafMeta(54, 39, ("VV", "VA")),
    "avwnomd": LeafMeta(54, 142, ("VV", "VA")),
    "avwnrg": LeafMeta(54, 129, ("VV", "VA")),
    "avwogre0": LeafMeta(54, 90, ("VV", "VA")),
    "avwogrx0": LeafMeta(54, 91, ("VV", "VA")),
    "avworc0": LeafMeta(54, 88, ("VV", "VA")),
    "avworcx0": LeafMeta(54, 89, ("VV", "VA")),
    "avwpeas": LeafMeta(54, 139, ("VV", "VA")),
    "avwpega0": LeafMeta(54, 20, ("VV", "VA")),
    "avwpegx0": LeafMeta(54, 21, ("VV", "VA")),
    "avwphx": LeafMeta(54, 131, ("VV", "VA")),
    "avwpike": LeafMeta(54, 0, ("VV", "VA")),
    "avwpikx0": LeafMeta(54, 1, ("VV", "VA")),
    "avwpitf0": LeafMeta(54, 50, ("VV", "VA")),
    "avwpitx0": LeafMeta(54, 51, ("VV", "VA")),
    "avwpixie": LeafMeta(54, 118, ("VV", "VA")),
    "avwpsye": LeafMeta(54, 120, ("VV", "VA")),
    "avwrdrg": LeafMeta(54, 82, ("VV", "VA")),
    "avwroc0": LeafMeta(54, 92, ("VV", "VA")),
    "avwrocx0": LeafMeta(54, 93, ("VV", "VA")),
    "avwrog": LeafMeta(54, 143, ("VV", "VA")),
    "avwrust": LeafMeta(54, 135, ("VV", "VA")),
    "avwsharp": LeafMeta(54, 137, ("VV", "VA")),
    "avwskel0": LeafMeta(54, 56, ("VV", "VA")),
    "avwskex0": LeafMeta(54, 57, ("VV", "VA")),
    "avwsprit": LeafMeta(54, 119, ("VV", "VA")),
    "avwstone": LeafMeta(54, 125, ("VV", "VA")),
    "avwstorm": LeafMeta(54, 127, ("VV", "VA")),
    "avwswrd0": LeafMeta(54, 6, ("VV", "VA")),
    "avwswrx0": LeafMeta(54, 7, ("VV", "VA")),
    "avwtitn0": LeafMeta(54, 40, ("VV", "VA")),
    "avwtitx0": LeafMeta(54, 41, ("VV", "VA")),
    "avwtree0": LeafMeta(54, 22, ("VV", "VA")),
    "avwtrex0": LeafMeta(54, 23, ("VV", "VA")),
    "avwtrll": LeafMeta(54, 144, ("VV", "VA")),
    "avwtrog0": LeafMeta(54, 70, ("VV", "VA")),
    "avwunic0": LeafMeta(54, 24, ("VV", "VA")),
    "avwunix0": LeafMeta(54, 25, ("VV", "VA")),
    "avwvamp0": LeafMeta(54, 62, ("VV", "VA")),
    "avwvamx0": LeafMeta(54, 63, ("VV", "VA")),
    "avwwigh": LeafMeta(54, 60, ("VV", "VA")),
    "avwwigx0": LeafMeta(54, 61, ("VV", "VA")),
    "avwwolf0": LeafMeta(54, 86, ("VV", "VA")),
    "avwwolx0": LeafMeta(54, 87, ("VV", "VA")),
    "avwwyvr": LeafMeta(54, 108, ("VV", "VA")),
    "avwwyvx0": LeafMeta(54, 109, ("VV", "VA")),
    "avwzomb0": LeafMeta(54, 58, ("VV", "VA")),
    "avwzomx0": LeafMeta(54, 59, ("VV", "VA")),
    "avxabnd0": LeafMeta(53, 7, ("VVVV", "VBXB")),
    "avxaltar": LeafMeta(2, 0, ("VVV", "VBX")),
    "avxamds": LeafMeta(220, 7, ("VVVV", "VBBB", "VBXB")),
    "avxamgr": LeafMeta(220, 7, ("VVV", "BXB")),
    "avxamlv": LeafMeta(220, 7, ("VVVV", "VVBV", "VBXB")),
    "avxamro": LeafMeta(220, 7, ("VVV", "VBB", "BXB")),
    "avxamsn": LeafMeta(220, 7, ("VVVV", "VVVV", "VBXB")),
    "avxamsu": LeafMeta(220, 7, ("VVVV", "VBXB")),
    "avxamsw": LeafMeta(220, 7, ("VVVV", "VBBB", "VBXB")),
    "avxbgt00": LeafMeta(212, 0, ("VVVV", "VBXB")),
    "avxbgt10": LeafMeta(212, 1, ("VVVV", "VBXB")),
    "avxbgt20": LeafMeta(212, 2, ("VVVV", "VBXB")),
    "avxbgt30": LeafMeta(212, 3, ("VVVV", "VBXB")),
    "avxbgt40": LeafMeta(212, 4, ("VVVV", "VBXB")),
    "avxbgt50": LeafMeta(212, 5, ("VVVV", "VBXB")),
    "avxbgt60": LeafMeta(212, 6, ("VVVV", "VBXB")),
    "avxbgt70": LeafMeta(212, 7, ("VVVV", "VBXB")),
    "avxbnk10": LeafMeta(16, 0, ("VVV", "VXB")),
    "avxbnk20": LeafMeta(16, 1, ("VVV", "VVV", "BXB")),
    "avxbnk30": LeafMeta(16, 2, ("VVV", "VVV", "VBX")),
    "avxbnk40": LeafMeta(16, 3, ("VVV", "VVV", "VBX")),
    "avxbnk50": LeafMeta(16, 4, ("VV", "XB")),
    "avxbnk60": LeafMeta(16, 5, ("VVV", "VVV", "VXB")),
    "avxbnk70": LeafMeta(16, 6, ("VVVV", "VVVV", "VVAV")),
    "avxboat0": LeafMeta(8, 0, ("VVV", "VAV")),
    "avxboat1": LeafMeta(8, 1, ("VVV", "VAV")),
    "avxboat2": LeafMeta(8, 2, ("VVV", "VAV")),
    "avxbor00": LeafMeta(9, 0, ("VV", "VA")),
    "avxbor10": LeafMeta(9, 1, ("VV", "VA")),
    "avxbor20": LeafMeta(9, 2, ("VV", "VA")),
    "avxbor30": LeafMeta(9, 3, ("VV", "VA")),
    "avxbor40": LeafMeta(9, 4, ("VV", "VA")),
    "avxbor50": LeafMeta(9, 5, ("VV", "VA")),
    "avxbor60": LeafMeta(9, 6, ("VV", "VA")),
    "avxbor70": LeafMeta(9, 7, ("VV", "VA")),
    "avxbor80": LeafMeta(215, 0, ("VV", "VA")),
    "avxbttl0": LeafMeta(59, 0, ("A",)),
    "avxccht0": LeafMeta(82, 0, ("A",)),
    "avxcf0": LeafMeta(222, 0, ("B",)),
    "avxcf1": LeafMeta(222, 0, ("B",)),
    "avxcf2": LeafMeta(222, 0, ("B",)),
    "avxcf3": LeafMeta(222, 0, ("B",)),
    "avxcf4": LeafMeta(222, 0, ("B",)),
    "avxcf5": LeafMeta(222, 0, ("B",)),
    "avxcf6": LeafMeta(222, 0, ("B",)),
    "avxcf7": LeafMeta(222, 0, ("B",)),
    "avxcfds0": LeafMeta(12, 0, ("A",)),
    "avxcflv0": LeafMeta(12, 0, ("A",)),
    "avxcfsn0": LeafMeta(12, 0, ("A",)),
    "avxcg1": LeafMeta(223, 0, ("B",)),
    "avxcg2": LeafMeta(223, 0, ("B",)),
    "avxcg3": LeafMeta(223, 0, ("B",)),
    "avxcg4": LeafMeta(223, 0, ("B",)),
    "avxcg5": LeafMeta(223, 0, ("B",)),
    "avxcg6": LeafMeta(223, 0, ("B",)),
    "avxcg7": LeafMeta(223, 0, ("B",)),
    "avxcovr0": LeafMeta(15, 0, ("VVV", "VVV", "VXB")),
    "avxcrsd0": LeafMeta(21, 0, ("B",)),
    "avxdend0": LeafMeta(97, 0, ("VV", "BX")),
    "avxdent": LeafMeta(97, 0, ("VV", "BX")),
    "avxef0": LeafMeta(224, 0, ("B",)),
    "avxef1": LeafMeta(224, 0, ("B",)),
    "avxef2": LeafMeta(224, 0, ("B",)),
    "avxef3": LeafMeta(224, 0, ("B",)),
    "avxef4": LeafMeta(224, 0, ("B",)),
    "avxef5": LeafMeta(224, 0, ("B",)),
    "avxef6": LeafMeta(224, 0, ("B",)),
    "avxef7": LeafMeta(224, 0, ("B",)),
    "avxeyem0": LeafMeta(27, 0, ("VV", "VA")),
    "avxff0": LeafMeta(226, 0, ("B",)),
    "avxff1": LeafMeta(226, 0, ("B",)),
    "avxff2": LeafMeta(226, 0, ("B",)),
    "avxff3": LeafMeta(226, 0, ("B",)),
    "avxff4": LeafMeta(226, 0, ("B",)),
    "avxff5": LeafMeta(226, 0, ("B",)),
    "avxff6": LeafMeta(226, 0, ("B",)),
    "avxff7": LeafMeta(226, 0, ("B",)),
    "avxfgld": LeafMeta(213, 0, ("VVVV", "VVVV", "VBXB")),
    "avxfw0": LeafMeta(225, 0, ("B",)),
    "avxfw1": LeafMeta(225, 0, ("B",)),
    "avxfw2": LeafMeta(225, 0, ("B",)),
    "avxfw3": LeafMeta(225, 0, ("B",)),
    "avxfw4": LeafMeta(225, 0, ("B",)),
    "avxfw5": LeafMeta(225, 0, ("B",)),
    "avxfw6": LeafMeta(225, 0, ("B",)),
    "avxfw7": LeafMeta(225, 0, ("B",)),
    "avxfyth0": LeafMeta(31, 0, ("VVV", "VBB", "VBX")),
    "avxgyds0": LeafMeta(84, 0, ("VVVV", "VBXB")),
    "avxgyne0": LeafMeta(84, 0, ("VVV", "BXB")),
    "avxgysn0": LeafMeta(84, 0, ("VVVV", "VBXB")),
    "avxhg0": LeafMeta(227, 0, ("B",)),
    "avxhg1": LeafMeta(227, 0, ("B",)),
    "avxhg2": LeafMeta(227, 0, ("B",)),
    "avxhg3": LeafMeta(227, 0, ("B",)),
    "avxhg4": LeafMeta(227, 0, ("B",)),
    "avxhg5": LeafMeta(227, 0, ("B",)),
    "avxhg6": LeafMeta(227, 0, ("B",)),
    "avxhg7": LeafMeta(227, 0, ("B",)),
    "avxhild0": LeafMeta(35, 0, ("VVV", "VVV", "VBX")),
    "avxhilg0": LeafMeta(35, 0, ("VVV", "VVV", "VBX")),
    "avxhutm0": LeafMeta(37, 0, ("VVV", "VVV", "VAV")),
    "avxkey00": LeafMeta(10, 0, ("VVV", "VBX")),
    "avxkey10": LeafMeta(10, 1, ("VVV", "VBX")),
    "avxkey20": LeafMeta(10, 2, ("VVV", "VBX")),
    "avxkey30": LeafMeta(10, 3, ("VVV", "VBX")),
    "avxkey40": LeafMeta(10, 4, ("VVV", "VBX")),
    "avxkey50": LeafMeta(10, 5, ("VVV", "VBX")),
    "avxkey60": LeafMeta(10, 6, ("VVV", "VBX")),
    "avxkey70": LeafMeta(10, 7, ("VVV", "VBX")),
    "avxl1sh0": LeafMeta(88, 0, ("VV", "VA")),
    "avxl2sh0": LeafMeta(89, 0, ("VV", "VA")),
    "avxl3sh0": LeafMeta(90, 0, ("VV", "VA")),
    "avxlp0": LeafMeta(228, 0, ("B",)),
    "avxlp1": LeafMeta(228, 0, ("B",)),
    "avxlp2": LeafMeta(228, 0, ("B",)),
    "avxlp3": LeafMeta(228, 0, ("B",)),
    "avxlp4": LeafMeta(228, 0, ("B",)),
    "avxlp5": LeafMeta(228, 0, ("B",)),
    "avxlp6": LeafMeta(228, 0, ("B",)),
    "avxlp7": LeafMeta(228, 0, ("B",)),
    "avxlths0": LeafMeta(42, 0, ("VVV", "VVV", "VVV", "VVA")),
    "avxmags0": LeafMeta(48, 0, ("VVV", "VVV", "VAA")),
    "avxmaps0": LeafMeta(13, 1, ("VV", "VV", "XB")),
    "avxmapu0": LeafMeta(13, 2, ("VVV", "VVV", "VXB")),
    "avxmapw0": LeafMeta(13, 0, ("VVV", "VVV", "VXB")),
    "avxmc0": LeafMeta(229, 0, ("B",)),
    "avxmc1": LeafMeta(229, 0, ("B",)),
    "avxmc2": LeafMeta(229, 0, ("B",)),
    "avxmc3": LeafMeta(229, 0, ("B",)),
    "avxmc4": LeafMeta(229, 0, ("B",)),
    "avxmc5": LeafMeta(229, 0, ("B",)),
    "avxmc6": LeafMeta(229, 0, ("B",)),
    "avxmc7": LeafMeta(229, 0, ("B",)),
    "avxmerm0": LeafMeta(52, 0, ("VVV", "BXB")),
    "avxmktb0": LeafMeta(7, 0, ("VVV", "VBX")),
    "avxmn1b0": LeafMeta(43, 0, ("V", "A")),
    "avxmn1r0": LeafMeta(43, 1, ("V", "A")),
    "avxmn1y0": LeafMeta(43, 2, ("V", "A")),
    "avxmn2g0": LeafMeta(45, 0, ("VV", "VA")),
    "avxmn2o0": LeafMeta(45, 1, ("VV", "VA")),
    "avxmn2p0": LeafMeta(45, 2, ("VV", "VA")),
    "avxmn4b0": LeafMeta(45, 3, ("V", "A")),
    "avxmn4i0": LeafMeta(43, 3, ("V", "A")),
    "avxmn4o0": LeafMeta(44, 3, ("V", "A")),
    "avxmn5b0": LeafMeta(45, 4, ("VVV", "VXB")),
    "avxmn5i0": LeafMeta(43, 4, ("VVV", "VXB")),
    "avxmn5o0": LeafMeta(44, 4, ("VVV", "VXB")),
    "avxmn6b0": LeafMeta(45, 5, ("VVV", "VXB")),
    "avxmn6i0": LeafMeta(43, 5, ("VVV", "VXB")),
    "avxmn6o0": LeafMeta(44, 5, ("VVV", "VXB")),
    "avxmn7b0": LeafMeta(45, 6, ("VVV", "VXB")),
    "avxmn7i0": LeafMeta(43, 6, ("VVV", "VXB")),
    "avxmn7o0": LeafMeta(44, 6, ("VVV", "VXB")),
    "avxmn8b0": LeafMeta(45, 7, ("VVV", "VXB")),
    "avxmn8i0": LeafMeta(43, 7, ("VVV", "VXB")),
    "avxmn8o0": LeafMeta(44, 7, ("VVV", "VXB")),
    "avxmp1": LeafMeta(230, 0, ("B",)),
    "avxmp2": LeafMeta(230, 0, ("B",)),
    "avxmp3": LeafMeta(230, 0, ("B",)),
    "avxmp4": LeafMeta(230, 0, ("B",)),
    "avxmp5": LeafMeta(230, 0, ("B",)),
    "avxmp6": LeafMeta(230, 0, ("B",)),
    "avxmp7": LeafMeta(230, 0, ("B",)),
    "avxmx1b0": LeafMeta(44, 0, ("V", "A")),
    "avxmx1r0": LeafMeta(44, 1, ("V", "A")),
    "avxmx1y0": LeafMeta(44, 2, ("V", "A")),
    "avxoblb": LeafMeta(57, 0, ("VV", "VA")),
    "avxoblg": LeafMeta(57, 0, ("VV", "VA")),
    "avxoblk": LeafMeta(57, 0, ("VV", "VA")),
    "avxoblo": LeafMeta(57, 0, ("VV", "VA")),
    "avxoblp": LeafMeta(57, 0, ("VV", "VA")),
    "avxoblw": LeafMeta(57, 0, ("VV", "VA")),
    "avxobly": LeafMeta(57, 0, ("VV", "VA")),
    "avxosis0": LeafMeta(56, 0, ("VVV", "VBB", "VXX")),
    "avxpllr0": LeafMeta(60, 0, ("VV", "VV", "VA")),
    "avxplns0": LeafMeta(46, 0, ("B",)),
    "avxpost0": LeafMeta(99, 0, ("VVV", "VVV", "VBX")),
    "avxprmd0": LeafMeta(63, 0, ("VV", "BX")),
    "avxprsn0": LeafMeta(62, 0, ("VVV", "VVV", "VBX")),
    "avxpssn": LeafMeta(221, 0, ("VVV", "VVV", "VBX")),
    "avxpstr0": LeafMeta(99, 0, ("VVV", "VVV", "VBX")),
    "avxreds0": LeafMeta(58, 0, ("VV", "VV", "VA")),
    "avxredw": LeafMeta(58, 0, ("VV", "VV", "VA")),
    "avxrk0": LeafMeta(231, 0, ("B",)),
    "avxrk1": LeafMeta(231, 0, ("B",)),
    "avxrk2": LeafMeta(231, 0, ("B",)),
    "avxrk3": LeafMeta(231, 0, ("B",)),
    "avxrk4": LeafMeta(231, 0, ("B",)),
    "avxrk5": LeafMeta(231, 0, ("B",)),
    "avxrk6": LeafMeta(231, 0, ("B",)),
    "avxrk7": LeafMeta(231, 0, ("B",)),
    "avxrlly0": LeafMeta(64, 0, ("VVV", "VBX")),
    "avxsanc0": LeafMeta(80, 0, ("VVV", "VVV", "VBX")),
    "avxschl0": LeafMeta(81, 0, ("VV", "VA")),
    "avxseeb0": LeafMeta(83, 2, ("VVV", "VVV", "VAV")),
    "avxseer0": LeafMeta(83, 0, ("VVV", "VAV")),
    "avxseey0": LeafMeta(83, 1, ("VVV", "VAV")),
    "avxshyd0": LeafMeta(87, 0, ("VVV", "VVV", "BXB")),
    "avxsirn0": LeafMeta(92, 0, ("VVVV", "VBXB")),
    "avxskds0": LeafMeta(22, 0, ("VA",)),
    "avxsndg0": LeafMeta(91, 0, ("A",)),
    "avxsnds0": LeafMeta(91, 0, ("A",)),
    "avxsnlv0": LeafMeta(91, 0, ("A",)),
    "avxsnsn0": LeafMeta(91, 0, ("A",)),
    "avxsnsw0": LeafMeta(91, 0, ("A",)),
    "avxstbl0": LeafMeta(94, 0, ("VVV", "VBX")),
    "avxtomb0": LeafMeta(108, 0, ("VVV", "VBX")),
    "avxtrek0": LeafMeta(102, 0, ("VVV", "VVV", "VAV")),
    "avxtvrn0": LeafMeta(95, 0, ("VVV", "VVV", "VVV", "VXB")),
    "avxwelg0": LeafMeta(49, 0, ("VV", "VA")),
    "avxwelr0": LeafMeta(49, 0, ("VV", "VA")),
    "avxwhrl0": LeafMeta(111, 0, ("AAA", "AAA")),
    "avxwlsn0": LeafMeta(49, 0, ("VV", "VA")),
    "avxwtrh0": LeafMeta(110, 0, ("VVVV", "AAAA")),
    "avzevnt0": LeafMeta(26, 0, ("VA",)),
    "avzgrail": LeafMeta(36, 0, ("VA",)),
    "clrdelt1": LeafMeta(143, 0, ("B",)),
    "clrdelt2": LeafMeta(143, 0, ("B",)),
    "clrdelt3": LeafMeta(143, 0, ("B",)),
    "clrdelt4": LeafMeta(143, 0, ("B",)),
    "icedelt1": LeafMeta(143, 0, ("B",)),
    "icedelt2": LeafMeta(143, 0, ("B",)),
    "icedelt3": LeafMeta(143, 0, ("B",)),
    "icedelt4": LeafMeta(143, 0, ("B",)),
    "lavdelt1": LeafMeta(143, 0, ("B",)),
    "lavdelt2": LeafMeta(143, 0, ("B",)),
    "lavdelt3": LeafMeta(143, 0, ("B",)),
    "lavdelt4": LeafMeta(143, 0, ("B",)),
    "muddelt1": LeafMeta(143, 0, ("B",)),
    "muddelt2": LeafMeta(143, 0, ("B",)),
    "muddelt3": LeafMeta(143, 0, ("B",)),
    "muddelt4": LeafMeta(143, 0, ("B",)),
}
# === END GENERATED LEAF_META ===


def build_tree() -> Taxonomy:
    """Return the full CLUSTER->PURPOSE->type->terrain->leaf taxonomy (the hardcoded TAXONOMY)."""
    return TAXONOMY


def iter_leaves(tree: Taxonomy | None = None) -> Iterator[tuple[str, str, str, str, str, str]]:
    """Yield (cluster, purpose, type, terrain, leaf_name, animation) for every leaf.

    A terrain node is a sorted list of animation DEFs (leaf name == animation) OR a
    {leaf_name: animation} dict (colour-keyed quest objects)."""
    tree = build_tree() if tree is None else tree
    for cluster, purposes in tree.items():
        for purpose, types in purposes.items():
            for typ, terrains in types.items():
                for terrain, leaves in terrains.items():
                    if isinstance(leaves, dict):
                        for name, anim in leaves.items():
                            yield cluster, purpose, typ, terrain, name, anim
                    else:
                        for anim in leaves:
                            yield cluster, purpose, typ, terrain, anim, anim


# ---------------------------------------------------------------------------
# Placement / category accessors — the ontology as the SINGLE SOURCE OF TRUTH for object
# identity, footprint mask, terrain coupling and decoration category. The whole generation
# pipeline (tile placement -> .vmap -> rendering) draws from these instead of the corpus.
# `type`/`subtype` in a placement identity come from `kit.vcmi_config` (same as the corpus path),
# so an ontology identity is a drop-in for the old objlib identity.
# ---------------------------------------------------------------------------


@cache
def _indexes() -> _Indexes:
    at: dict[str, set[str]] = {}
    ac: dict[str, str] = {}
    dbt: dict[str, set[str]] = {}
    gbt: dict[tuple[str, str], set[str]] = {}
    for cluster, purpose, typ, terrain, _name, anim in iter_leaves(TAXONOMY):
        at.setdefault(anim, set()).add(terrain)
        if cluster == "DECORATION":
            ac[anim] = typ
            dbt.setdefault(terrain, set()).add(anim)
        else:
            gbt.setdefault((terrain, purpose), set()).add(anim)  # gameplay leaves by purpose
    return _Indexes(
        anim_terrains=at,
        anim_category=ac,
        veg_categories=sorted(set(ac.values())),
        decor_by_terrain={t: sorted(a) for t, a in dbt.items()},
        gameplay_by_tp={k: sorted(a) for k, a in gbt.items()},
    )


def _terrain_name(terrain: str | int) -> str:
    return terrain if isinstance(terrain, str) else TERRAIN_NAMES.get(terrain, "")


def has_animation(animation: str) -> bool:
    """True if the ontology carries placement metadata for this animation (case-insensitive)."""
    return (animation or "").lower() in LEAF_META


def mask_of(animation: str) -> Mask:
    """B/A/V footprint rows for an animation (`kit.objects.mask_cells` semantics: rows are
    stored LEFT-TO-RIGHT, sprite-aligned, so column 0 is the LEFTMOST tile and the anchor is
    the last column, `tx = ax - (ww - 1 - c)`; case-insensitive), V-padded to the sprite's full
    tile extent (see :func:`_decode_mask_full`) — the same extent AND column order `.vmap`
    export uses (see :func:`vmap_mask_of`), so gameplay placement never lands another object
    (or a guard's own approach) on a tile the sprite visually covers."""
    m = LEAF_META.get((animation or "").lower())
    return m.mask if m else ("B",)


def vmap_mask_of(animation: str) -> Mask | None:
    """The VCMI-charset (` 0VBHAT`) template mask for .vmap export (case-insensitive):
    `mask_of` with 'X' entrance cells translated to VCMI's 'A' (VISIBLE|BLOCKED|VISITABLE) —
    same column order, no reversal (see :func:`mask_of`); this is the exact charset/order real
    VCMI RMG `.vmap` templates use (verified byte-for-byte against 30 real sawmill instances).
    None when the ontology does not know the animation."""
    m = LEAF_META.get((animation or "").lower())
    if not m:
        return None
    return tuple(r.replace("X", "A") for r in m.mask)


def cls_sub_of(animation: str) -> tuple[int, int] | tuple[None, None]:
    m = LEAF_META.get((animation or "").lower())
    return (m.cls, m.sub) if m else (None, None)


def is_blocking(animation: str) -> bool:
    """True if the object's footprint blocks movement (its mask has a 'B' or 'X' cell)."""
    return any(ch in "BX" for row in mask_of(animation) for ch in row)


def footprint_size(animation: str) -> int:
    """Bounding-box area of the footprint (sum of row lengths) — matches the corpus convention."""
    return sum(len(row) for row in mask_of(animation))


def identity_of(animation: str) -> Identity:
    """Placement ``Identity`` (type, subtype, animation, mask) for an animation — a drop-in for
    the corpus objlib identity, sourced entirely from the ontology + objects.txt metadata."""
    cls, sub = cls_sub_of(animation)
    r = vcmi_config.resolve(cls, sub) if cls is not None and sub is not None else None
    return Identity(
        type=r[0] if r else None,
        subtype=r[1] if r else None,
        animation=animation,
        mask=mask_of(animation),
    )


def terrains_of(animation: str) -> set[str]:
    """Set of terrain-node names an animation appears under in the taxonomy (case-insensitive)."""
    return set(_indexes().anim_terrains.get((animation or "").lower(), ()))


def allowed_on(animation: str, terrain: str | int) -> bool:
    """True if the animation may stand on a terrain. Terrain-specific tags beat the generic
    'land' tag, which admits any non-water terrain. An animation the ontology does not know is
    allowed nowhere."""
    tags = terrains_of(animation)
    if not tags:
        return False
    name = _terrain_name(terrain)
    specific = tags - {"land"}
    if specific:
        return name in specific
    return name not in ("water", "")


def _decor_keys(name: str) -> list[str]:
    """Terrain-node keys to pull DECORATION from for a terrain: the terrain itself plus the
    terrain-independent 'land'/'water' bucket (generic obstacles usable anywhere)."""
    keys = [name]
    if name == "water":
        keys.append("water")
    elif name != "rock":
        keys.append("land")
    return keys


def decor_pool(
    terrain: str | int,
    *,
    blocking: bool | None = None,
    max_cells: int | None = None,
    exclude_types: Iterable[str] = (),
) -> list[Identity]:
    """DECORATION placement identities native to a terrain (name or id), filtered by optional
    predicates: ``blocking`` (footprint blocks or not), ``max_cells`` (bounding-box area cap),
    ``exclude_types`` (ontology type-level names to drop, e.g. water features)."""
    idx = _indexes()
    name = _terrain_name(terrain)
    exclude = set(exclude_types)
    out: list[Identity] = []
    seen: set[str] = set()
    for k in _decor_keys(name):
        for anim in idx.decor_by_terrain.get(k, ()):
            if anim in seen or idx.anim_category.get(anim) in exclude:
                continue
            if blocking is not None and is_blocking(anim) != blocking:
                continue
            if max_cells is not None and footprint_size(anim) > max_cells:
                continue
            seen.add(anim)
            out.append(identity_of(anim))
    return out


def gameplay_pool(terrain: str | int, purpose: str) -> list[Identity]:
    """Placement identities for a gameplay PURPOSE (TOWN, MINE, DWELLING, REWARD_PICKUP, …) native
    to
    a terrain plus the terrain-independent 'land' bucket. The ontology enumerator used when the
    corpus
    grammar's idents for a purpose are thin/absent, so visitables and resources are always
    placeable.
    Returns ``Identity`` values (drop-in for corpus idents); zero corpus."""
    idx = _indexes()
    name = _terrain_name(terrain)
    out: list[Identity] = []
    seen: set[str] = set()
    for k in _decor_keys(name):
        for anim in idx.gameplay_by_tp.get((k, purpose), ()):
            if anim in seen:
                continue
            seen.add(anim)
            out.append(identity_of(anim))
    return out


def mines_by_resource(terrain: str | int) -> dict[str, list[Identity]]:
    """``{resource: [identity]}`` for MINE objects placeable on a terrain — the resource bucket
    (wood,
    ore, gold, …) is the ontology-resolved subtype (``kit.vcmi_config`` -> :data:`MINE_RES`). Lets
    a town
    economy guarantee a wood + ore mine without touching the corpus."""
    out: dict[str, list[Identity]] = {}
    for ident in gameplay_pool(terrain, "MINE"):
        sub = ident.subtype
        res = str(sub)
        out.setdefault(res, []).append(ident)
    return out


def spell_level(name: str) -> int | None:
    """A spell's mage-guild level (1-5), or ``None`` if `name` isn't a real hero-castable
    spell (a creature-only special ability, or not a recognized VCMI spell identifier)."""
    return SPELL_LEVELS.get(name)


def spells_by_level(level: int) -> list[str]:
    """Sorted list of spell identifiers at mage-guild `level` (1-5)."""
    return sorted(n for n, lvl in SPELL_LEVELS.items() if lvl == level)


def artifact_tier(name: str) -> str | None:
    """An artifact's rarity tier ('treasure'/'minor'/'major'/'relic'), or ``None`` if
    `name` isn't a randomly-obtainable artifact (a war machine, the Spell Book/Scroll,
    the Grail, or not a recognized VCMI artifact identifier)."""
    return ARTIFACT_TIERS.get(name)


def artifacts_by_tier(tier: str) -> list[str]:
    """Sorted list of artifact identifiers in rarity `tier`
    ('treasure'/'minor'/'major'/'relic')."""
    return sorted(n for n, t in ARTIFACT_TIERS.items() if t == tier)


def monster_level(name: str) -> int | None:
    """A creature's town tier (1-7; 0 for war machines/siege equipment), or ``None`` if
    `name` isn't a recognized VCMI creature identifier."""
    return MONSTER_LEVELS.get(name)


def monsters_by_level(level: int) -> list[str]:
    """Sorted list of creature identifiers at town tier `level`."""
    return sorted(n for n, lvl in MONSTER_LEVELS.items() if lvl == level)


def visitable_purposes() -> tuple[str, ...]:
    """Gameplay purposes that are 'visitable' destinations — the guaranteed-minimum set so a zone is
    never left with nothing to visit (a regression guard for the group-placement budget)."""
    return ("MINE", "DWELLING", "STAT_PERMANENT", "SPELL_SKILL", "BONUS_TEMP", "MANA")


def veg_categories() -> list[str]:
    """The decoration category vocabulary = the ontology DECORATION type-level keys."""
    return list(_indexes().veg_categories)


def category_of(animation: str) -> int | None:
    """Index of an animation's decoration category in :func:`veg_categories` (None if not decor;
    case-insensitive)."""
    idx = _indexes()
    typ = idx.anim_category.get((animation or "").lower())
    return idx.veg_categories.index(typ) if typ in idx.veg_categories else None


def pool(
    object_class: str,
    terrain: str | int,
    *,
    blocking: bool | None = None,
    max_cells: int | None = None,
    exclude_types: Iterable[str] = (),
) -> list[Identity]:
    """Every identity of an object class that may stand on a terrain. ``object_class`` is a
    gameplay purpose (MINE, DWELLING, ...) or a decoration category (CRATER, mountain, ...).
    Terrain-specific tags beat the generic 'land' tag. Empty when the class has nothing native
    to that terrain."""
    idx = _indexes()
    if object_class in idx.veg_categories:
        return [
            i
            for i in decor_pool(
                terrain, blocking=blocking, max_cells=max_cells, exclude_types=exclude_types
            )
            if idx.anim_category.get(i.animation) == object_class
        ]
    return [
        i
        for i in gameplay_pool(terrain, object_class)
        if (blocking is None or is_blocking(i.animation) == blocking)
        and (max_cells is None or footprint_size(i.animation) <= max_cells)
        and idx.anim_category.get(i.animation) not in set(exclude_types)
    ]


def pick(object_class: str, terrain: str | int, rng: Random) -> Identity | None:
    """One identity of an object class allowed on a terrain, drawn uniformly with ``rng``.
    None when the class has nothing native to that terrain."""
    candidates = sorted(pool(object_class, terrain), key=lambda i: i.animation)
    return rng.choice(candidates) if candidates else None


def decode_identity(
    category: int | str | None, terrain: str | int, rng: Random | None = None
) -> Identity | None:
    """Pick a concrete DECORATION identity of a category (index or type name) native to a terrain
    (falls back to the terrain-independent 'land' bucket). Uniform; deterministic if rng is None."""
    idx = _indexes()
    if isinstance(category, str):
        typ = category
    elif category is not None and 0 <= category < len(idx.veg_categories):
        typ = idx.veg_categories[category]
    else:
        return None
    candidates = pool(typ, terrain)
    if not candidates:
        return None
    if rng is None:
        return candidates[0]
    return pick(typ, terrain, rng)


def category_terrain_matrix() -> list[list[bool]]:
    """bool[len(TERRAIN_NAMES)][len(categories)]: a category is present on a terrain (incl. the
    terrain-independent 'land'/'water' bucket) in the taxonomy."""
    idx = _indexes()
    cidx = {t: i for i, t in enumerate(idx.veg_categories)}
    M = [[False] * len(idx.veg_categories) for _ in range(len(TERRAIN_NAMES))]
    for tid, name in TERRAIN_NAMES.items():
        for k in _decor_keys(name):
            for anim in idx.decor_by_terrain.get(k, ()):
                cat = idx.anim_category.get(anim)
                c = cidx.get(cat) if cat is not None else None
                if c is not None:
                    M[tid][c] = True
    return M


# ---------------------------------------------------------------------------
# Regeneration: derive the taxonomy from the AUTHORITATIVE VCMI/H3 object table
# (objects.txt in the LOD) -- the absolute list the map editor places -- and rewrite
# the TAXONOMY literal above in place. Run: `python -m vcmi_mapgen.ontology --regen`.
# objects.txt columns: DEF, passability(48), triggers(48), allowedTerrains(9),
# nativeTerrain(9), class, subclass, group, isOverlay. The 9-bit terrain masks are
# MSB->LSB = terrain 8..0 (water..dirt); bit i means terrain (8 - i).
# ---------------------------------------------------------------------------


def _decode_mask(passability: str, triggers: str) -> Mask:
    """Decode the objects.txt passability(48)+triggers(48) bitfields into the B/A/V footprint
    mask rows (`kit.objects.mask_cells` semantics: B=blocking, A=visitable anchor, V=visible
    overlay). This reproduces `kit.vmap.mask.build_mask_from_h3m` (the corpus mask source)
    bit-for-bit: the
    6x8 grid defaults to 'V', a cell is 'A' if its trigger bit is set else 'B' if its
    passability bit is clear (H3: clear=blocked); rows/cols that are all-'V' are trimmed. The
    grid is anchored bottom-right and stored rotated 180° (rows bottom-to-top AND columns
    right-to-left), so BOTH are reversed to sprite-align it — reversing rows only leaves every
    asymmetric footprint horizontally mirrored vs the art (the v5.2 sawmill-entrance bug; see
    :func:`_decode_mask_grid`). Kept bit-for-bit in sync with `kit.vmap.mask.build_mask_from_h3m`
    (the
    corpus mask source)."""

    def rows(bits: str) -> list[str]:
        return [bits[r * 8 : (r + 1) * 8] for r in range(6)]

    P, T = rows(passability), rows(triggers)
    grid = [["V"] * 8 for _ in range(6)]
    for r in range(6):
        for c in range(8):
            blocked = P[r][c] == "0"  # H3: passability bit clear == blocked
            visit = T[r][c] == "1"
            # four states from two independent bits; 'X' = blocked AND visitable (building action
            # tile, visited from an adjacent tile) — keep its blocked-ness instead of collapsing to
            # A
            grid[r][c] = ("X" if blocked else "A") if visit else ("B" if blocked else "V")
    # only an object with a solid BODY ('B' cells) keeps a blocked visit tile ('X', visited from
    # adjacent); a bodyless single visit tile is a walk-onto pickup -> 'A' (passable). See
    # build_mask.
    if not any(grid[r][c] == "B" for r in range(6) for c in range(8)):
        for r in range(6):
            for c in range(8):
                if grid[r][c] == "X":
                    grid[r][c] = "A"
    grid = [row[::-1] for row in grid[::-1]]  # 180°: rows bottom-to-top, cols right-to-left
    keep_r = [r for r in range(6) if any(ch != "V" for ch in grid[r])]
    keep_c = [c for c in range(8) if any(grid[r][c] != "V" for r in range(6))]
    if not keep_r or not keep_c:
        return ("B",)
    return tuple("".join(grid[r][c] for c in keep_c) for r in keep_r)


def _decode_mask_grid(passability: str, triggers: str) -> Mask:
    """Return the FULL 6x8 visual footprint grid (rows top->bottom, cols left->right) aligned to
    the SPRITE, WITHOUT trimming -- what an editor-style overlay needs. H3 object masks are anchored
    at the BOTTOM-RIGHT and read bottom-to-top, RIGHT-to-LEFT, so the storage grid is rotated 180°
    (rows reversed AND columns reversed) to put it sprite-aligned. (Reversing rows only -- as the
    placement decoder :func:`_decode_mask` does -- leaves asymmetric footprints horizontally
    MIRRORED vs the art: e.g. a pine clump's blocked trunks, or a sawmill's visit tile, land on the
    wrong side.) '.' marks a tile outside the footprint (not drawn); a passable tile INSIDE the
    active bounding box is 'V' (overhang)."""
    grid = _storage_mask_grid(passability, triggers)
    if not any(grid[r][c] == "B" for r in range(6) for c in range(8)):
        _demote_entrances(grid)
    grid = [row[::-1] for row in grid[::-1]]  # 180°: rows bottom-to-top, cols right-to-left
    _fill_overhang(grid)
    return tuple("".join(row) for row in grid)


def _storage_mask_grid(passability: str, triggers: str) -> list[list[str]]:
    def rows(bits: str) -> list[str]:
        return [bits[r * 8 : (r + 1) * 8] for r in range(6)]

    P, T = rows(passability), rows(triggers)
    grid = [["."] * 8 for _ in range(6)]
    for r in range(6):
        for c in range(8):
            blocked = P[r][c] == "0"
            visit = T[r][c] == "1"
            grid[r][c] = ("X" if blocked else "A") if visit else ("B" if blocked else ".")
    return grid


def _demote_entrances(grid: list[list[str]]) -> None:
    for r in range(6):
        for c in range(8):
            if grid[r][c] == "X":
                grid[r][c] = "A"


def _fill_overhang(grid: list[list[str]]) -> None:
    act = [(r, c) for r in range(6) for c in range(8) if grid[r][c] != "."]
    if act:  # passable tiles inside the footprint bbox -> 'V'
        r0, r1 = min(r for r, _ in act), max(r for r, _ in act)
        c0, c1 = min(c for _, c in act), max(c for _, c in act)
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                if grid[r][c] == ".":
                    grid[r][c] = "V"


@cache
def _full_grids() -> dict[str, Mask]:
    grids: dict[str, Mask] = {}
    for anim, p1, p2 in _objects_txt_raw():
        if len(p1) == 48 and len(p2) == 48:
            grids[anim] = _decode_mask_grid(p1, p2)
    return grids


def full_mask_of(animation: str) -> Mask | None:
    """The full 6-row x 8-col visual footprint grid (B/X/A/V/'.') for an animation, bottom-left
    anchored -- for editor-style overlays. Empty ('.') outside the object footprint. See
    :func:`_decode_mask_grid`."""
    return _full_grids().get((animation or "").lower())


def _def_tile_dims(animation: str) -> tuple[int, int] | None:
    """(width, height) of an animation's sprite in 32px TILES, from the DEF file header in the
    H3 LOD (type u32, width u32, height u32). None when the DEF is absent."""
    data = lod().read(animation + ".def")
    if not data or len(data) < 12:
        return None
    _typ, w, h = struct.unpack_from("<III", data, 0)
    if not (0 < w <= 8 * 32 and 0 < h <= 6 * 32):
        return None
    return ((w + 31) // 32, (h + 31) // 32)


def _decode_mask_full(passability: str, triggers: str, tile_dims: tuple[int, int] | None) -> Mask:
    """The bottom-right window of the full sprite-aligned footprint grid
    (:func:`_decode_mask_grid`), sized to the sprite's tile extent — 'X' entrances kept
    distinct from plain visitable 'A' (see :func:`vmap_mask_of`, which translates X->A). VCMI
    draws an object only on mask-covered tiles, so a mask trimmed to the blocked bbox
    (:func:`_decode_mask`) truncates tall sprites in-game and is too small for gameplay
    placement too: it lets other objects (or a guard's own approach search) land on tiles that
    are visually part of the sprite (the v5.3 sawmill-guard-hidden-behind-trees bug). Real RMG
    .vmaps V-fill to the sprite extent, so this is the ground truth for :func:`mask_of` as well
    as :func:`vmap_mask_of` — both in the same LEFT-TO-RIGHT column order as this function's
    output and the corpus's `kit.vmap.mask.build_mask_from_h3m` masks (col 0 = leftmost tile,
    anchor is the
    last column: `tx = ax - (ww - 1 - c)`, see `kit.objects.mask_cells`'s docstring); no column
    reversal is needed anywhere in this decode chain — the v5.4 sawmill-guard-wrong-side bug
    turned out to be in the CONSUMER (`mask_cells`/`_cells` treating col 0 as the anchor instead
    of the leftmost tile), not in this decode chain."""
    grid = _decode_mask_grid(passability, triggers)  # 6 rows x 8 cols, '.' outside
    act = [(r, c) for r in range(6) for c in range(8) if grid[r][c] != "."]
    if not act:
        return ("B",)
    wt, ht = tile_dims if tile_dims else (0, 0)
    ht = max(1, min(6, ht), 6 - min(r for r, _ in act))  # never cut an active cell
    wt = max(1, min(8, wt), 8 - min(c for _, c in act))
    return tuple(
        "".join("V" if ch == "." else ch for ch in grid[r][8 - wt :]) for r in range(6 - ht, 6)
    )


def _objects_txt_raw() -> list[tuple[str, str, str]]:
    """[(animation, passability48, triggers48), ...] straight from objects.txt (no decode)."""
    raw = lod().read("objects.txt")
    if raw is None:
        raise RuntimeError("objects.txt not found in the H3 LOD")
    out: list[tuple[str, str, str]] = []
    for line in raw.decode("latin1", "replace").splitlines()[1:]:
        p = line.split()
        if len(p) < 7 or not p[0].lower().endswith(".def"):
            continue
        anim = p[0][:-4].lower()
        if anim == "default":
            continue
        out.append((anim, p[1], p[2]))
    return out


def _objects_txt_records() -> list[tuple[str, str, str, int, int, Mask]]:
    """[(animation, allowedMask, nativeMask, class, subclass, mask), ...] from the LOD's
    objects.txt. ``mask`` is the decoded B/A/V footprint (see :func:`_decode_mask`)."""
    raw = lod().read("objects.txt")
    if raw is None:
        raise RuntimeError("objects.txt not found in the H3 LOD")
    recs: list[tuple[str, str, str, int, int, Mask]] = []
    for line in raw.decode("latin1", "replace").splitlines()[1:]:
        p = line.split()
        if len(p) < 7 or not p[0].lower().endswith(".def"):
            continue
        anim = p[0][:-4].lower()
        if anim == "default":
            continue
        mask = _decode_mask(p[1], p[2]) if len(p[1]) == 48 and len(p[2]) == 48 else ("B",)
        recs.append((anim, p[3], p[4], int(p[5]), int(p[6]), mask))
    return recs


def _mask_terrains(mask: str) -> set[str]:
    """9-bit objects.txt terrain mask -> set of land/water terrain names (bit i -> terrain 8-i)."""
    return {TERRAIN_NAMES[8 - i] for i, c in enumerate(mask) if c == "1"}


def _template_terrains(allowed_mask: str, native_mask: str, coupled: bool) -> list[str]:
    """Terrain node(s) for a template: the native terrain(s) for terrain-coupled objects, else a
    coarse land/water bucket (terrain-independent objects carry a placeholder native terrain)."""
    if coupled:
        native = sorted(_mask_terrains(native_mask))
        if not native:
            return ["land"]
        if len([t for t in native if t != "water"]) >= 8:  # native to (essentially) all land
            return ["land"]
        return native
    allowed = _mask_terrains(allowed_mask)
    if "water" in allowed and not any(t != "water" for t in allowed):
        return ["water"]
    return ["land"]


def _derive_leaf_meta() -> dict[str, LeafMeta]:
    """{animation: {"cls", "sub", "mask"}} for every objects.txt template — the per-animation
    placement metadata the ontology exposes via :func:`identity_of` / :func:`mask_of`, windowed
    to the sprite's full tile extent and already in `mask_cells`'s anchor convention
    (:func:`_decode_mask_full`), so the same footprint serves gameplay placement AND (with X->A)
    `.vmap` export (:func:`vmap_mask_of`) with no reversal in between."""
    bits = {anim: (p1, p2) for anim, p1, p2 in _objects_txt_raw()}
    meta: dict[str, LeafMeta] = {}
    for anim, _allowed, _native, cls, sub, mask in _objects_txt_records():
        p1, p2 = bits.get(anim, ("", ""))
        if len(p1) == 48 and len(p2) == 48:
            leaf_mask = _decode_mask_full(p1, p2, _def_tile_dims(anim))
        else:
            leaf_mask = mask
        meta[anim] = LeafMeta(cls, sub, leaf_mask)
    return meta


def _derive_taxonomy() -> Taxonomy:
    """Build the CLUSTER->PURPOSE->type->terrain->leaf tree from objects.txt + the ontology."""
    raw: dict[str, dict[str, dict[str, dict[str, dict[str, str]]]]] = {}
    for anim, allowed, native, cls, sub, _mask in _objects_txt_records():
        r = resolve(cls, sub)
        typ = r.name
        if typ in COLOR_KEYED_NAMES:
            leaf_name = GATE_COLORS.get(sub, str(sub))
        elif typ in SUBTYPE_KEYED_NAMES:
            leaf_name = r.subtype  # faction (castle, rampart, ...)
        else:
            leaf_name = anim
        for terrain in _template_terrains(allowed, native, r.terrain_coupled):
            node = (
                raw.setdefault(r.cluster, {})
                .setdefault(r.purpose, {})
                .setdefault(typ, {})
                .setdefault(terrain, {})
            )
            node[leaf_name] = anim
    # compact each terrain node: a plain sorted list when leaf names == animations, else a dict.
    tree: Taxonomy = {}
    for cluster, purposes in raw.items():
        for purpose, types in purposes.items():
            for typ, terrains in types.items():
                for terr, leaves in terrains.items():
                    compact: list[str] | dict[str, str] = (
                        sorted(leaves.values())
                        if all(k == v for k, v in leaves.items())
                        else leaves
                    )
                    tree.setdefault(cluster, {}).setdefault(purpose, {}).setdefault(typ, {})[
                        terr
                    ] = compact
    return tree


type _FmtNode = str | list[str] | Mapping[str, _FmtNode]


def _fmt(obj: _FmtNode, ind: int = 0) -> str:
    """Pretty-print the taxonomy as compact Python source (nested dicts indented; leaves inline)."""
    sp = "    " * ind
    if isinstance(obj, str):
        return json.dumps(obj)
    if isinstance(obj, list):
        return "[" + ", ".join(json.dumps(x) for x in obj) + "]"
    if obj and all(isinstance(v, str) for v in obj.values()):
        return "{" + ", ".join(f"{json.dumps(k)}: {json.dumps(v)}" for k, v in obj.items()) + "}"
    items = [f"{sp}    {json.dumps(k)}: {_fmt(obj[k], ind + 1)}" for k in sorted(obj)]
    return "{\n" + ",\n".join(items) + f"\n{sp}}}"


_BEGIN = "# === BEGIN GENERATED TAXONOMY"
_END = "# === END GENERATED TAXONOMY ==="
_META_BEGIN = "# === BEGIN GENERATED LEAF_META ==="
_META_END = "# === END GENERATED LEAF_META ==="


def _fmt_leaf_meta(meta: dict[str, LeafMeta]) -> str:
    """One compact line per animation: `"anim": LeafMeta(C, S, ("row", ...)),`."""
    lines: list[str] = []
    for anim in sorted(meta):
        m = meta[anim]
        rows = ", ".join(json.dumps(row) for row in m.mask)
        mask = f"({rows},)" if len(m.mask) == 1 else f"({rows})"
        lines.append(f"    {json.dumps(anim)}: LeafMeta({m.cls}, {m.sub}, {mask}),")
    return "{\n" + "\n".join(lines) + "\n}"


def _rewrite_block(src: str, begin: str, end: str, text: str) -> str:
    """Replace the body between a BEGIN marker line and its END marker with ``text``."""
    head = src[: src.index("\n", src.index(begin)) + 1]
    tail = src[src.index(end) :]
    return f"{head}{text}\n{tail}"


def regenerate() -> Taxonomy:
    """Derive the taxonomy + per-animation placement metadata from objects.txt and rewrite
    both the TAXONOMY and LEAF_META literals in this file."""
    tree = _derive_taxonomy()
    meta = _derive_leaf_meta()
    os.makedirs(os.path.dirname(TREE_CACHE), exist_ok=True)
    with open(TREE_CACHE, "w") as fh:
        json.dump(tree, fh, indent=1, sort_keys=True)
    path = os.path.join(_HERE, "ontology.py")
    with open(path) as fh:
        src = fh.read()
    src = _rewrite_block(src, _BEGIN, _END, f"TAXONOMY: Taxonomy = {_fmt(tree)}")
    src = _rewrite_block(
        src, _META_BEGIN, _META_END, f"LEAF_META: dict[str, LeafMeta] = {_fmt_leaf_meta(meta)}"
    )
    with open(path, "w") as fh:
        _ = fh.write(src)
    return tree


class Ontology:
    """Object-facts facade: the abstraction layer between raw game data and the
    pipeline. Every ``PipelineStep``'s ``run(ontology, map_state)`` receives ONE shared
    instance of this class (see ``pipeline.py``) so a step never needs to hardcode an
    object's identity/mask/terrain coupling — it asks the ontology instead. Each method
    just delegates to this module's own top-level accessor of the same name; the class
    exists so the pipeline holds and passes a single object, not the bare module."""

    def cluster_of(self, purpose: str, name: str | None = None, type_: str | None = None) -> str:
        return cluster_of(purpose, name=name, type_=type_)

    def name_of(self, cid: int) -> str:
        return name_of(cid)

    def resolve(self, cid: int, subclass: int) -> ClassInfo:
        return resolve(cid, subclass)

    def build_tree(self) -> Taxonomy:
        return build_tree()

    def iter_leaves(
        self, tree: Taxonomy | None = None
    ) -> Iterator[tuple[str, str, str, str, str, str]]:
        return iter_leaves(tree)

    def has_animation(self, animation: str) -> bool:
        return has_animation(animation)

    def mask_of(self, animation: str) -> Mask:
        return mask_of(animation)

    def vmap_mask_of(self, animation: str) -> Mask | None:
        return vmap_mask_of(animation)

    def cls_sub_of(self, animation: str) -> tuple[int, int] | tuple[None, None]:
        return cls_sub_of(animation)

    def is_blocking(self, animation: str) -> bool:
        return is_blocking(animation)

    def footprint_size(self, animation: str) -> int:
        return footprint_size(animation)

    def identity_of(self, animation: str) -> Identity:
        return identity_of(animation)

    def terrains_of(self, animation: str) -> set[str]:
        return terrains_of(animation)

    def allowed_on(self, animation: str, terrain: str | int) -> bool:
        return allowed_on(animation, terrain)

    def pool(
        self,
        object_class: str,
        terrain: str | int,
        *,
        blocking: bool | None = None,
        max_cells: int | None = None,
        exclude_types: Iterable[str] = (),
    ) -> list[Identity]:
        return pool(
            object_class,
            terrain,
            blocking=blocking,
            max_cells=max_cells,
            exclude_types=exclude_types,
        )

    def pick(self, object_class: str, terrain: str | int, rng: Random) -> Identity | None:
        return pick(object_class, terrain, rng)

    def decor_pool(
        self,
        terrain: str | int,
        *,
        blocking: bool | None = None,
        max_cells: int | None = None,
        exclude_types: Iterable[str] = (),
    ) -> list[Identity]:
        return decor_pool(
            terrain, blocking=blocking, max_cells=max_cells, exclude_types=exclude_types
        )

    def gameplay_pool(self, terrain: str | int, purpose: str) -> list[Identity]:
        return gameplay_pool(terrain, purpose)

    def mines_by_resource(self, terrain: str | int) -> dict[str, list[Identity]]:
        return mines_by_resource(terrain)

    def visitable_purposes(self) -> tuple[str, ...]:
        return visitable_purposes()

    def veg_categories(self) -> list[str]:
        return veg_categories()

    def category_of(self, animation: str) -> int | None:
        return category_of(animation)

    def decode_identity(
        self, category: int | str | None, terrain: str | int, rng: Random | None = None
    ) -> Identity | None:
        return decode_identity(category, terrain, rng=rng)

    def category_terrain_matrix(self) -> list[list[bool]]:
        return category_terrain_matrix()

    def full_mask_of(self, animation: str) -> Mask | None:
        return full_mask_of(animation)


if __name__ == "__main__":
    import sys

    tr = regenerate() if "--regen" in sys.argv else build_tree()
    n_leaf = sum(1 for _ in iter_leaves(tr))
    print(f"ontology taxonomy ({'regenerated' if '--regen' in sys.argv else 'hardcoded'})")
    for cluster in CLUSTERS:
        purposes = tr.get(cluster, {})
        types = sum(len(t) for t in purposes.values())
        leaves = sum(1 for x in iter_leaves(tr) if x[0] == cluster)
        print(f"  {cluster:11s} purposes={len(purposes):2d} types={types:3d} leaves={leaves}")
    print(f"  total leaves: {n_leaf}")

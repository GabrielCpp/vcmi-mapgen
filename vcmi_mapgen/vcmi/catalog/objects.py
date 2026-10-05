"""Catalog queries over the object tables: identity, footprint, terrain coupling, pools.

The catalog is the SINGLE SOURCE OF TRUTH for object identity, footprint mask, terrain coupling
and decoration category. The whole generation pipeline (tile placement -> .vmap -> rendering)
draws from these instead of the corpus. `type`/`subtype` in a placement identity come from
`vcmi.config`, the same as the corpus path.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache

from vcmi_mapgen.core.model import Identity
from vcmi_mapgen.core.model.artifact import ArtifactSet
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.vcmi import terrain as vterrain
from vcmi_mapgen.vcmi.catalog.tables import (
    DECOR_NAMES,
    FACTION,
    GATE_NAMES,
    GATE_TYPES,
    MINE_RES,
    PURPOSE,
    RELATIONAL,
    RESOURCE,
    TERRAIN_COUPLED,
    ClassInfo,
    Taxonomy,
    artifact_sets,
    artifact_tiers,
    class_names,
    leaf_meta,
    monster_levels,
    spell_levels,
    taxonomy,
    vcmi_class_types,
    vcmi_type_classes,
)
from vcmi_mapgen.vcmi.config import EMPTY_CONFIG, VcmiConfig
from vcmi_mapgen.vcmi.footprint import Mask, footprint_of


@dataclass(frozen=True, slots=True)
class _Indexes:
    anim_terrains: dict[str, set[str]]
    anim_category: dict[str, str]
    veg_categories: list[str]
    decor_by_terrain: dict[str, list[str]]
    gameplay_by_tp: dict[tuple[str, str], list[str]]


def cluster_of(purpose: str, name: str | None = None, type_: str | None = None) -> str:
    """Macro-cluster for an object, from its purpose plus (when QUEST_GATE) its enum name
    or VCMI `type`. Usable from both the enum-name path (resolve) and the type path (the
    catalog renderer)."""
    if purpose == "DECORATION":
        return "DECORATION"
    if purpose == "TRANSPORT":
        return "QUEST_PAIR"
    if purpose == "QUEST_GATE":
        if name in GATE_NAMES or type_ in GATE_TYPES:
            return "GATE"
        return "QUEST_PAIR"
    return "VISIBLE"


# class ids that are pure visual obstacles (incl. the once-unnamed AB decor classes
# 177/199/206-211, now named LAKE_2 / TREES_2 / *_HILLS / SUBTERRANEAN_ROCKS / SWAMP_FOLIAGE)
def _is_decoration(name: str) -> bool:
    if name.startswith("CLASS_"):  # enum gap -> decorative obstacle
        return True
    return name in DECOR_NAMES


def name_of(cid: int) -> str:
    return class_names().get(cid, f"CLASS_{cid}")


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


def build_tree() -> Taxonomy:
    """Return the full CLUSTER->PURPOSE->type->terrain->leaf taxonomy from
    ``data/catalog/taxonomy.json``."""
    return taxonomy()


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


@cache
def indexes() -> _Indexes:
    at: dict[str, set[str]] = {}
    ac: dict[str, str] = {}
    dbt: dict[str, set[str]] = {}
    gbt: dict[tuple[str, str], set[str]] = {}
    for cluster, purpose, typ, terrain, _name, anim in iter_leaves(taxonomy()):
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


def terrain_name(terrain: str | int) -> str:
    return terrain if isinstance(terrain, str) else vterrain.name_of(terrain)


def has_animation(animation: str) -> bool:
    """True if the ontology carries placement metadata for this animation (case-insensitive)."""
    return (animation or "").lower() in leaf_meta()


def mask_of(animation: str) -> Mask:
    """B/A/V footprint rows for an animation (`vcmi.footprint.footprint_of` semantics: rows are
    stored LEFT-TO-RIGHT, sprite-aligned, so column 0 is the LEFTMOST tile and the anchor is
    the last column, `tx = ax - (ww - 1 - c)`; case-insensitive), V-padded to the sprite's full
    tile extent (see :func:`_decode_mask_full`) — the same extent AND column order `.vmap`
    export uses (see :func:`vmap_mask_of`), so gameplay placement never lands another object
    (or a guard's own approach) on a tile the sprite visually covers."""
    m = leaf_meta().get((animation or "").lower())
    return m.mask if m else ("B",)


def vmap_mask_of(animation: str) -> Mask | None:
    """The VCMI-charset (` 0VBHAT`) template mask for .vmap export (case-insensitive):
    `mask_of` with 'X' entrance cells translated to VCMI's 'A' (VISIBLE|BLOCKED|VISITABLE) —
    same column order, no reversal (see :func:`mask_of`); this is the exact charset/order real
    VCMI RMG `.vmap` templates use (verified byte-for-byte against 30 real sawmill instances).
    None when the ontology does not know the animation."""
    m = leaf_meta().get((animation or "").lower())
    if not m:
        return None
    return tuple(r.replace("X", "A") for r in m.mask)


def cls_sub_of(animation: str) -> tuple[int, int] | tuple[None, None]:
    m = leaf_meta().get((animation or "").lower())
    return (m.cls, m.sub) if m else (None, None)


def static_type(animation: str) -> tuple[str | None, int | None, int | None]:
    """The VCMI type, class id and subtype id of an animation, read from the checked-in
    tables alone, so the answer holds with no VCMI install."""
    cls, sub = cls_sub_of(animation)
    if cls is None:
        return None, None, None
    return vcmi_class_types().get(cls), cls, sub


def is_blocking(animation: str) -> bool:
    """True if the object's footprint blocks movement (its mask has a 'B' or 'X' cell)."""
    return any(ch in "BX" for row in mask_of(animation) for ch in row)


def footprint_size(animation: str) -> int:
    """Bounding-box area of the footprint (sum of row lengths) — matches the corpus convention."""
    return sum(len(row) for row in mask_of(animation))


_CONFIG: list[VcmiConfig] = [EMPTY_CONFIG]


def use_config(config: VcmiConfig) -> None:
    _CONFIG[0] = config


def identity_of(animation: str) -> Identity:
    """Placement ``Identity`` (type, subtype, animation, mask) for an animation, sourced
    entirely from the ontology + objects.txt metadata."""
    cls, sub = cls_sub_of(animation)
    r = _CONFIG[0].resolve(cls, sub) if cls is not None and sub is not None else None
    return Identity(
        type=r[0] if r else None,
        subtype=r[1] if r else None,
        kind=animation,
        footprint=footprint_of(mask_of(animation)),
    )


def terrains_of(animation: str) -> set[str]:
    """Set of terrain-node names an animation appears under in the taxonomy (case-insensitive)."""
    return set(indexes().anim_terrains.get((animation or "").lower(), ()))


def allowed_on(animation: str, terrain: str | int) -> bool:
    """True if the animation may stand on a terrain. Terrain-specific tags beat the generic
    'land' tag, which admits any non-water terrain. An animation the ontology does not know is
    allowed nowhere."""
    tags = terrains_of(animation)
    if not tags:
        return False
    name = terrain_name(terrain)
    specific = tags - {"land"}
    if specific:
        return name in specific
    return name not in ("water", "")


def terrain_keys(name: str) -> list[str]:
    """Terrain-node keys to pull DECORATION from for a terrain: the terrain itself plus the
    terrain-independent 'land'/'water' bucket (generic obstacles usable anywhere)."""
    keys = [name]
    if name == "water":
        keys.append("water")
    elif name != "rock":
        keys.append("land")
    return keys


def gameplay_pool(terrain: str | int, purpose: str) -> list[Identity]:
    """Placement identities for a gameplay PURPOSE (TOWN, MINE, DWELLING, REWARD_PICKUP, …) native
    to
    a terrain plus the terrain-independent 'land' bucket. The ontology enumerator used when the
    corpus
    grammar's idents for a purpose are thin/absent, so visitables and resources are always
    placeable.
    Returns ``Identity`` values (drop-in for corpus idents); zero corpus."""
    idx = indexes()
    name = terrain_name(terrain)
    out: list[Identity] = []
    seen: set[str] = set()
    for k in terrain_keys(name):
        for anim in idx.gameplay_by_tp.get((k, purpose), ()):
            if anim in seen:
                continue
            seen.add(anim)
            out.append(identity_of(anim))
    return out


def mines_by_resource(terrain: str | int) -> dict[str, list[Identity]]:
    """``{resource: [identity]}`` for MINE objects placeable on a terrain — the resource bucket
    (wood,
    ore, gold, …) is the ontology-resolved subtype (``vcmi.config`` -> :data:`MINE_RES`). Lets
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
    return spell_levels().get(name)


def spells_by_level(level: int) -> list[str]:
    """Sorted list of spell identifiers at mage-guild `level` (1-5)."""
    return sorted(n for n, lvl in spell_levels().items() if lvl == level)


def artifact_tier(name: str) -> str | None:
    """An artifact's rarity tier ('treasure'/'minor'/'major'/'relic'), or ``None`` if
    `name` isn't a randomly-obtainable artifact (a war machine, the Spell Book/Scroll,
    the Grail, or not a recognized VCMI artifact identifier)."""
    return artifact_tiers().get(name)


def artifacts_by_tier(tier: str) -> list[str]:
    """Sorted list of artifact identifiers in rarity `tier`
    ('treasure'/'minor'/'major'/'relic')."""
    return sorted(n for n, t in artifact_tiers().items() if t == tier)


def monster_level(name: str) -> int | None:
    """A creature's town tier (1-7; 0 for war machines/siege equipment), or ``None`` if
    `name` isn't a recognized VCMI creature identifier."""
    return monster_levels().get(name)


def monsters_by_level(level: int) -> list[str]:
    """Sorted list of creature identifiers at town tier `level`."""
    return sorted(n for n, lvl in monster_levels().items() if lvl == level)


def purpose_of_type(type_name: str | None) -> Purpose | None:
    """The purpose of a VCMI object type, through its class id, or ``None`` when the type is
    unknown."""
    cid = vcmi_type_classes().get(type_name) if type_name is not None else None
    return None if cid is None else Purpose(resolve(cid, 0).purpose)


def artifact_set_table() -> list[ArtifactSet]:
    """Every combined artifact whose parts all carry a rarity tier, by name."""
    return [
        ArtifactSet(name, tuple(row["parts"]), row["water"])
        for name, row in sorted(artifact_sets().items())
        if all(artifact_tier(p) for p in row["parts"])
    ]


def artifact_pickup(name: str) -> Identity | None:
    """The pickup that places the named artifact, or ``None`` when the ontology has none."""
    for (_terrain, purpose), anims in sorted(indexes().gameplay_by_tp.items()):
        if purpose != "REWARD_PICKUP":
            continue
        for anim in anims:
            ident = identity_of(anim)
            if ident.subtype == name and ident.type == "artifact":
                return ident
    return None

"""Loot-zone fill: the treasure placed inside a sealed loot zone once its access is built."""

from __future__ import annotations

import random
import re
from collections.abc import Collection, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import Self

from vcmi_mapgen import ontology as ON
from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.models import CoverIndex, Identity, PlacedObject, Tile, ZoneRecord
from vcmi_mapgen.steps.gameplay import mines as PG
from vcmi_mapgen.steps.placement import PlaceSpec, PlaceTarget, place_one

_LOOT_ART_W = {"avarnd1": 5, "avarnd2": 15, "avarnd3": 35, "avarnd4": 45}
LOOT_EXCL_DECOR = frozenset({"LAKE", "FROZEN_LAKE", "RIVER_DELTA", "KELP", "REEF", "LAKE_2"})
FILL_EXCL_ANIMS = frozenset({"avsfntn0", "avsidol0"})
_LOOT_ART_EXCL_TYPES = frozenset({"leanTo", "wagon", "warriorTomb", "denOfThieves"})
LOOT_CHEST_TYPES = ("treasureChest", "campfire", "pandoraBox")
_LOOT_ZONE_CHEST_EXTRA_TYPES = ("scholar",)
_LOOT_SCROLL_LEVELS = (4, 5)
_LOOT_HERO_STRUCTURE_TYPES = frozenset({"learningStone", "gardenOfRevelation", "starAxis"})
_LOOT_HERO_STRUCTURE_COUNT = 2
LOOT_HERO_STRUCTURE_MIN_SEP = 2
_LOOT_RARE_RESOURCE_SUBTYPES = frozenset({"mercury", "sulfur", "crystal", "gems", "gold"})
_SOLO_VIS_PURPOSES = ("BONUS_TEMP", "SPELL_SKILL", "MANA", "STAT_PERMANENT")
_DIRS8 = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]


def shrine_spell_level(anim: str) -> int:
    """The spell level of a shrine animation, or 0 for anything that is not a shrine."""
    m = re.match(r"avxl(\d)sh", anim, re.IGNORECASE)
    return int(m.group(1)) if m else 0


def solo_visit_pool(
    terrain: str,
    exclude_anims: Collection[str] = (),
    min_shrine_level: int | None = None,
) -> list[Identity]:
    """Objects with exactly one visit tile and no blocking body cells, so they are safe to
    cache inside pockets."""
    seen: set[str] = set()
    out: list[Identity] = []
    for purpose in _SOLO_VIS_PURPOSES:
        for ident in ON.pool(purpose, terrain):
            anim = ident.animation.lower()
            if anim in seen or anim in exclude_anims:
                continue
            if min_shrine_level is not None and 0 < shrine_spell_level(anim) < min_shrine_level:
                continue
            n_visit = sum(ch in "AX" for row in ident.mask for ch in row)
            n_body = sum(ch == "B" for row in ident.mask for ch in row)
            if n_visit == 1 and n_body == 0:
                seen.add(anim)
                out.append(ident)
    return out


@dataclass(frozen=True, slots=True)
class _LootPools:
    pool_vis: list[Identity]
    pool_art: list[Identity]
    pool_res: list[Identity]
    chest_kind_pools: dict[str, list[Identity]]
    arts_high: list[tuple[str, int]]
    pool_rare: list[Identity]

    @classmethod
    def of(cls, terrain: str) -> Self:
        pool_vis = [
            i for i in ON.pool("STAT_PERMANENT", terrain) if i.type in _LOOT_HERO_STRUCTURE_TYPES
        ]
        pool_art = [
            i for i in ON.pool("REWARD_PICKUP", terrain) if i.type not in _LOOT_ART_EXCL_TYPES
        ]
        pool_res = ON.pool("RESOURCE_PILE", terrain)
        kinds = LOOT_CHEST_TYPES + _LOOT_ZONE_CHEST_EXTRA_TYPES
        pool_chest = [i for i in pool_art if i.type in kinds]
        chest_kind_pools = {kind: [i for i in pool_chest if i.type == kind] for kind in kinds}
        chest_kind_pools["spellScroll"] = [
            Identity(type="spellScroll", subtype=n, animation="ava0001", mask=("A",))
            for lvl in _LOOT_SCROLL_LEVELS
            for n in ON.spells_by_level(lvl)
        ]
        return cls(
            pool_vis=pool_vis,
            pool_art=pool_art,
            pool_res=pool_res,
            chest_kind_pools=chest_kind_pools,
            arts_high=[(a, _LOOT_ART_W[a]) for a in ("avarnd3", "avarnd4")],
            pool_rare=[i for i in pool_res if i.subtype in _LOOT_RARE_RESOURCE_SUBTYPES],
        )


@dataclass(frozen=True, slots=True)
class FillZone:
    """One sealed loot zone to fill: its walkable interior, the tiles already taken, and the
    gate or monolith footprint that must stay clear of decoration."""

    zid: int
    terrain: str
    st: PG.TerrainStats
    reach: frozenset[Tile]
    used: set[Tile]
    rng: random.Random
    all_ts: AbstractSet[Tile]
    footprint: AbstractSet[Tile]


def _fill_background(zone: FillZone, objs_out: list[PlacedObject], cover: CoverIndex) -> None:
    outside = zone.all_ts - zone.reach
    interior = {
        t for t in zone.reach if not any((t[0] + dx, t[1] + dy) in outside for dx, dy in _DIRS8)
    }
    pool_bg = ON.decor_pool(
        zone.terrain, blocking=False, max_cells=1, exclude_types=LOOT_EXCL_DECOR
    )
    if not pool_bg:
        return
    for t in sorted(interior):
        if zone.rng.random() < 0.5:
            o = PlacedObject.at(zone.rng.choice(pool_bg), t, purpose="")
            if cover.try_add(o):
                objs_out.append(o)


def _fill_hero_structures(zone: FillZone, pools: _LootPools, target: PlaceTarget) -> None:
    free = sorted(zone.reach - zone.used)
    zone.rng.shuffle(free)
    for struct_type in sorted(_LOOT_HERO_STRUCTURE_TYPES):
        candidates = [i for i in pools.pool_vis if i.type == struct_type]
        if not candidates:
            continue
        spec = PlaceSpec(
            "BONUS_TEMP", None, ident=zone.rng.choice(candidates), cache=True, interactive_only=True
        )
        placed: list[Tile] = []
        for t in free:
            if len(placed) >= _LOOT_HERO_STRUCTURE_COUNT:
                break
            if t in zone.used or _too_close(t, placed):
                continue
            if place_one(target, spec, *t):
                placed.append(t)


def _too_close(t: Tile, placed: Sequence[Tile]) -> bool:
    return any(
        max(abs(t[0] - p[0]), abs(t[1] - p[1])) < LOOT_HERO_STRUCTURE_MIN_SEP for p in placed
    )


def _roll_spec(
    rng: random.Random, pools: _LootPools, chest_kinds: Sequence[str]
) -> PlaceSpec | None:
    roll = rng.random()
    if roll < 0.2 and pools.arts_high:
        anim = rng.choices(
            [a for a, _ in pools.arts_high], weights=[w for _, w in pools.arts_high], k=1
        )[0]
        ident = ON.identity_of(anim)
        return PlaceSpec(
            "REWARD_PICKUP", pools.pool_art, ident=ident, cache=True, interactive_only=True
        )
    if roll < 0.6 and chest_kinds:
        ident = rng.choice(pools.chest_kind_pools[rng.choice(chest_kinds)])
        return PlaceSpec(
            "REWARD_PICKUP", pools.pool_art, ident=ident, cache=True, interactive_only=True
        )
    if pools.pool_rare:
        return PlaceSpec(
            "RESOURCE_PILE",
            pools.pool_res,
            ident=rng.choice(pools.pool_rare),
            cache=True,
            interactive_only=True,
        )
    return None


def _fill_rolls(zone: FillZone, pools: _LootPools, target: PlaceTarget) -> None:
    chest_kinds = [k for k, p in pools.chest_kind_pools.items() if p]
    for t in sorted(zone.reach - zone.used):
        spec = _roll_spec(zone.rng, pools, chest_kinds)
        if spec is not None:
            _ = place_one(target, spec, *t)


def _fill_decor(zone: FillZone, t: Tile, objs_out: list[PlacedObject], cover: CoverIndex) -> bool:
    pool = ON.decor_pool(zone.terrain, blocking=True, max_cells=1, exclude_types=LOOT_EXCL_DECOR)
    if not pool:
        return False
    o = PlacedObject.at(zone.rng.choice(pool), t, purpose="")
    if not cover.try_add(o):
        return False
    zone.used.add(t)
    objs_out.append(o)
    return True


def _fill_tile(
    zone: FillZone, pools: _LootPools, target: PlaceTarget, t: Tile, cover: CoverIndex
) -> bool:
    if pools.pool_rare:
        spec = PlaceSpec(
            "RESOURCE_PILE",
            pools.pool_res,
            ident=zone.rng.choice(pools.pool_rare),
            cache=True,
            interactive_only=True,
        )
        if place_one(target, spec, *t):
            return True
    spec = PlaceSpec("RESOURCE_PILE", pools.pool_res, cache=True, interactive_only=True)
    if place_one(target, spec, *t):
        return True
    return t not in zone.footprint and _fill_decor(zone, t, target.objs, cover)


def _fill_remaining(
    zone: FillZone, pools: _LootPools, target: PlaceTarget, cover: CoverIndex
) -> None:
    for t in sorted(zone.reach - zone.used):
        if t in zone.used:
            continue
        if not _fill_tile(zone, pools, target, t, cover):
            print(
                f"  WARNING: loot zone fill left tile {t} unclaimed "
                + f"(no fitting identity for terrain {zone.terrain!r})"
            )


def fill_loot_zone(
    zone: FillZone,
    objs_out: list[PlacedObject],
    cover: CoverIndex,
    bounds: tuple[int, int] | None,
) -> None:
    """Fill one sealed loot zone: passable background decor, hero structures, rolled loot,
    then a resource or a blocking decoration on every tile still free."""
    pools = _LootPools.of(zone.terrain)
    target = PlaceTarget(
        objs_out, zone.used, zone.reach, zone.rng, zone.st, bounds=bounds, cover=cover
    )
    _fill_background(zone, objs_out, cover)
    _fill_hero_structures(zone, pools, target)
    _fill_rolls(zone, pools, target)
    _fill_remaining(zone, pools, target, cover)


def fill_loot_zones(
    zone_records: Sequence[ZoneRecord],
    footprints: Mapping[int, frozenset[Tile]],
    level_objs: Sequence[PlacedObject],
    seed: int,
    bounds: tuple[int, int] | None,
) -> list[PlacedObject]:
    """Fill every loot zone of one level. ``footprints`` maps each loot zone id to its access
    object's footprint. Every record's ``used`` grows by the tiles the fill claimed."""
    cover = CoverIndex(level_objs)
    blocked: set[Tile] = {
        (cx, cy) for o in level_objs for cx, cy, blk in OR.mask_cells(o.mask, o.x, o.y) if blk
    }
    interactive = {c for o in level_objs for c in OR.mask_interactive_cells(o.mask, o.x, o.y)}
    all_ts: set[Tile] = set()
    for zr in zone_records:
        all_ts |= zr.ts
    new: list[PlacedObject] = []
    for zr in zone_records:
        footprint = footprints.get(zr.zid)
        if footprint is None:
            continue
        used = set(zr.ts & blocked) | (zr.ts & interactive) | footprint
        zone = FillZone(
            zid=zr.zid,
            terrain=zr.terrain,
            st=PG.mine_gameplay()[zr.terrain],
            reach=frozenset(zr.ts - blocked - footprint),
            used=used,
            rng=random.Random(seed ^ (zr.zid * 92821) ^ 0xA117),
            all_ts=all_ts,
            footprint=footprint,
        )
        fill_loot_zone(zone, new, cover, bounds)
        zr.used |= used
    return new

"""Loot-zone fill: the treasure placed inside a sealed loot zone once its access is built."""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass

from vcmi_mapgen.core.catalog import Catalog, Trait
from vcmi_mapgen.core.grid.geometry import NB8
from vcmi_mapgen.core.model import CoverIndex, Identity, PlacedObject, PlacementRule, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.placement.place import PlaceSpec, PlaceTarget, place_one
from vcmi_mapgen.core.placement.prizes import (
    HeldPrize,
    Hold,
    PrizePools,
    artifact_spec,
    fallback_specs,
    hold_prize,
    place_boxes,
)
from vcmi_mapgen.core.placement.room import RoomRule
from vcmi_mapgen.core.planning.zone_index import ZoneRecord
from vcmi_mapgen.core.priors.effort import Offer
from vcmi_mapgen.core.priors.gameplay import GameplayStats, TerrainStats

_LOOT_HERO_STRUCTURE_COUNT = 2
LOOT_HERO_STRUCTURE_MIN_SEP = 2


def _hero_pool(catalog: Catalog, terrain: str) -> list[Identity]:
    return [
        i
        for i in catalog.candidates(Purpose.STAT_PERMANENT, terrain)
        if i.type in catalog.types_with(Trait.HERO_BOOST)
    ]


@dataclass(frozen=True, slots=True)
class FillZone:
    """One sealed loot zone to fill: its walkable interior, the gate or monolith footprint
    that must stay clear of decoration, and what its band offers."""

    terrain: str
    st: TerrainStats
    reach: frozenset[Tile]
    all_ts: AbstractSet[Tile]
    footprint: AbstractSet[Tile]
    offer: Offer

    def interior(self) -> frozenset[Tile]:
        """The reach tiles with no 8-neighbour outside the reach and inside the level's zones."""
        outside = self.all_ts - self.reach
        return frozenset(
            t for t in self.reach if not any((t[0] + dx, t[1] + dy) in outside for dx, dy in NB8)
        )


@dataclass(frozen=True, slots=True)
class _Walk:
    """What the one pass reads beside the tile: the zone, its pools, the interior that takes
    background decor, the chosen hero structure per type and the placement target."""

    zone: FillZone
    pools: PrizePools
    interior: frozenset[Tile]
    heroes: Mapping[str, Identity]
    target: PlaceTarget


def _hero_choices(rng: random.Random, pool: Sequence[Identity]) -> dict[str, Identity]:
    types = sorted({i.type for i in pool if i.type is not None})
    return {k: rng.choice([i for i in pool if i.type == k]) for k in types}


def _hero_type(
    rng: random.Random, t: Tile, left: int, placed: Mapping[str, Sequence[Tile]]
) -> str | None:
    """Selection sampling: with `left` tiles still to walk, a hero structure lands here with
    the chance its unplaced count over `left`, so the structures spread over the zone in one
    pass. The type is the least placed one with room that keeps its minimum separation at
    `t`, so every type appears before any appears twice."""
    owed = sum(_LOOT_HERO_STRUCTURE_COUNT - len(ts) for ts in placed.values())
    if owed <= 0 or rng.random() * left >= owed:
        return None
    fits = [
        (len(ts), kind)
        for kind, ts in placed.items()
        if len(ts) < _LOOT_HERO_STRUCTURE_COUNT and not _too_close(t, ts)
    ]
    return min(fits)[1] if fits else None


def _too_close(t: Tile, placed: Sequence[Tile]) -> bool:
    return any(
        max(abs(t[0] - p[0]), abs(t[1] - p[1])) < LOOT_HERO_STRUCTURE_MIN_SEP for p in placed
    )


def _background(walk: _Walk, t: Tile) -> None:
    pool = walk.target.catalog.decor(walk.zone.terrain, blocking=False, max_cells=1)
    if t in walk.interior and pool and walk.target.rng.random() < 0.5:
        o = PlacedObject.at(walk.target.rng.choice(pool), t, purpose="")
        if walk.target.cover.try_add(o):
            walk.target.objs.append(o)


def _blocking_decor(walk: _Walk, t: Tile) -> bool:
    pool = walk.target.catalog.decor(walk.zone.terrain, blocking=True, max_cells=1)
    if t in walk.zone.footprint or not pool:
        return False
    o = PlacedObject.at(walk.target.rng.choice(pool), t, purpose="")
    if not walk.target.cover.try_claim(o, [t]):
        return False
    walk.target.objs.append(o)
    return True


def _passable_decor(walk: _Walk, t: Tile) -> bool:
    if walk.target.cover.covers_at(t):
        walk.target.cover.claim([t])
        return True
    pool = walk.target.catalog.decor(walk.zone.terrain, blocking=False, max_cells=1)
    if not pool:
        return False
    o = PlacedObject.at(walk.target.rng.choice(pool), t, purpose="")
    if not walk.target.cover.try_claim(o, [t]):
        return False
    walk.target.objs.append(o)
    return True


def _hero(walk: _Walk, t: Tile, kind: str) -> bool:
    ident = walk.heroes[kind]
    spec = PlaceSpec(Purpose.BONUS_TEMP, None, ident=ident, cache=True, interactive_only=True)
    return place_one(walk.target, spec, *t)


def _loot(walk: _Walk, t: Tile) -> bool:
    """The first of these that lands at `t`: the rolled loot, a rare resource, any resource,
    a blocking decoration, then a passable decoration where a blocking one would split the
    room."""
    specs = fallback_specs(walk.target.rng, walk.pools, walk.zone.offer)
    landed = any(place_one(walk.target, spec, *t) for spec in specs)
    return landed or _blocking_decor(walk, t) or _passable_decor(walk, t)


def _deepest(walk: _Walk, tiles: Sequence[Tile]) -> list[Tile]:
    """``tiles`` from the farthest from the opener in."""

    def depth(t: Tile) -> int:
        return min(max(abs(t[0] - f[0]), abs(t[1] - f[1])) for f in walk.zone.footprint)

    return sorted(tiles, key=lambda t: (-depth(t), t))


def _headline(walk: _Walk, tiles: Sequence[Tile]) -> Hold | None:
    """Hold back the free tile farthest from the opener that takes an artifact of the band's
    basket, then stand the band's Pandora's Boxes on the deepest tiles left."""
    spec = artifact_spec(walk.target.rng, walk.pools, walk.zone.offer.basket)
    if spec is None or not walk.zone.footprint:
        return None
    held = hold_prize(walk.target, spec, _deepest(walk, tiles))
    _ = place_boxes(walk.target, walk.pools, walk.zone.offer, _deepest(walk, tiles))
    return held


def fill_loot_zone(
    catalog: Catalog,
    zone: FillZone,
    rng: random.Random,
    cover: CoverIndex,
    bounds: tuple[int, int] | None,
) -> tuple[list[PlacedObject], Hold | None]:
    """Fill one sealed loot zone: a held slot for an artifact of its band at the back and its
    band's Pandora's Boxes beside it, then one pass over its free tiles. A tile takes the
    hero structure due there, or else a passable background decoration and then the first
    of rolled loot, a resource or a blocking decoration that lands there."""
    pools = PrizePools.of(catalog, zone.terrain)
    objs: list[PlacedObject] = []
    target = PlaceTarget(catalog, objs, cover, zone.reach, rng, zone.st, bounds=bounds)
    heroes = _hero_choices(rng, _hero_pool(catalog, zone.terrain))
    walk = _Walk(zone, pools, zone.interior(), heroes, target)
    placed: dict[str, list[Tile]] = {k: [] for k in walk.heroes}
    held = _headline(walk, sorted(zone.reach - cover.claims))
    tiles = sorted(zone.reach - cover.claims)
    for i, t in enumerate(tiles):
        hero = _hero_type(rng, t, len(tiles) - i, placed)
        if hero is not None and _hero(walk, t, hero):
            placed[hero].append(t)
            continue
        _background(walk, t)
        if t not in cover.claims and not _loot(walk, t):
            print(
                f"  WARNING: loot zone fill left tile {t} unclaimed "
                + f"(no fitting identity for terrain {zone.terrain!r})"
            )
    return objs, held


@dataclass(frozen=True, slots=True)
class LootLevel:
    """One level to fill: every zone record, the access footprint and the band offer of each
    loot zone by zone id, the objects already on the level, the gameplay statistics per terrain
    and the tiles the level has claimed, and the rules every new object must pass."""

    zone_records: Sequence[ZoneRecord]
    footprints: Mapping[int, frozenset[Tile]]
    offers: Mapping[int, Offer]
    objs: Sequence[PlacedObject]
    gameplay: GameplayStats
    claims: frozenset[Tile] = frozenset()
    rules: Sequence[PlacementRule] = ()
    level: int = 0


@dataclass(frozen=True, slots=True)
class LootFill:
    """What one level's fill left: the new objects, the level's claims grown by the tiles the
    fill claimed, and the slot each loot zone held back, by zone id."""

    objs: list[PlacedObject]
    claims: frozenset[Tile]
    held: dict[int, HeldPrize]


def fill_loot_zones(
    catalog: Catalog, level: LootLevel, seed: int, bounds: tuple[int, int] | None
) -> LootFill:
    """Fill every loot zone of one level."""
    zone_records, footprints, level_objs = level.zone_records, level.footprints, level.objs
    blocked: set[Tile] = {
        (cx, cy)
        for o in level_objs
        for cx, cy, blk in FP.anchored_cells(o.footprint, o.x, o.y)
        if blk
    }
    interactive = {c for o in level_objs for c in FP.interactive_cells(o.footprint, o.x, o.y)}
    reaches = {
        zr.zid: frozenset(zr.ts - blocked - interactive)
        for zr in zone_records
        if zr.zid in footprints
    }
    cover = CoverIndex(level_objs, level.claims, (*level.rules, RoomRule(reaches.values())))
    all_ts: set[Tile] = set()
    for zr in zone_records:
        all_ts |= zr.ts
    new: list[PlacedObject] = []
    held: dict[int, HeldPrize] = {}
    for zr in zone_records:
        footprint = footprints.get(zr.zid)
        if footprint is None:
            continue
        cover.claim((zr.ts & blocked) | (zr.ts & interactive))
        zone = FillZone(
            terrain=zr.terrain,
            st=level.gameplay[zr.terrain],
            reach=reaches[zr.zid],
            all_ts=all_ts,
            footprint=footprint,
            offer=level.offers[zr.zid],
        )
        rng = random.Random(seed ^ (zr.zid * 92821) ^ 0xA117)
        objs, hold = fill_loot_zone(catalog, zone, rng, cover, bounds)
        new.extend(objs)
        if hold is not None:
            held[zr.zid] = hold.at(level.level, zr.terrain)
    return LootFill(new, frozenset(cover.claims), held)

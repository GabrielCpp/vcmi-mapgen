"""Guarded pocket caches: a guard at each pocket mouth, an artifact at the deepest tile
and pickups in between, placed once per level over the finished walkable field. The
artifact's tier follows the guard's level through `ART_TIER_BY_GUARD_LEVEL`, so the guard's
strength matches the prize behind it."""

import random
from collections.abc import Collection, Container, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import final

from vcmi_mapgen.core.catalog import ArtifactTier, Catalog
from vcmi_mapgen.core.grid.pockets import POCKET_MAX_TILES, find_pockets, pocket_depths
from vcmi_mapgen.core.model import CoverIndex, Identity, PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.placement.guards import guard_spaced
from vcmi_mapgen.core.placement.place import PlaceSpec, PlaceTarget, place_one
from vcmi_mapgen.core.planning.zone_index import ZoneRecord
from vcmi_mapgen.core.priors.gameplay import GameplayStats, TerrainStats
from vcmi_mapgen.core.steps.loot.pockets import (
    dedupe_pockets,
    guard_stand,
    guard_stands,
    home_mine_protect_pairs,
    reach8,
    reachable,
)
from vcmi_mapgen.core.steps.treasure.fill import (
    FILL_EXCL_TYPES,
    LOOT_CHEST_TYPES,
    solo_visit_pool,
)

ART_TIER_BY_GUARD_LEVEL: tuple[ArtifactTier | None, ...] = (
    "treasure",
    "treasure",
    "minor",
    "major",
    "major",
    None,
)

# Types that must maintain a minimum map-fraction separation between any two instances in pockets.
_POCKET_SPACED_TYPES = frozenset({"magicWell", "warriorTomb"})


@dataclass(frozen=True, slots=True)
class PocketContext:
    gameplay: GameplayStats
    border_guards: Container[Tile] = ()
    precomputed_pockets: Mapping[Tile, tuple[frozenset[Tile], frozenset[Tile]]] | None = None
    existing_objs: Sequence[PlacedObject] = ()
    home_zids: Collection[int] = ()
    cover: CoverIndex | None = None


def place_pocket_caches(
    catalog: Catalog,
    zone_records: Sequence[ZoneRecord],
    context: PocketContext,
    seed: int = 1,
    bounds: tuple[int, int] | None = None,
) -> tuple[list[PlacedObject], int, dict[Tile, float]]:
    """Guarded caches in genuine geometric pockets — found in ONE global, zone-independent
    pass over the WHOLE map's TRUE physical passability, run once after every zone's
    terrain, vegetation and scatter is finalized. `zone_records` is a list of
    {"zid", "terrain", "ts", "open_set", "passable", "reach"}: `open_set` is that
    zone's PLACEMENT-ELIGIBLE tiles (terrain minus vegetation-blocked/gameplay-occupied/
    approach cells — nothing new may stack there); `passable` is that zone's TRUE physical
    passability (terrain minus only the tiles that are actually impassable — approach tiles
    and non-blocking occupied footprint cells stay in it, since a hero can walk over them
    even though nothing new can be placed there); `reach` as returned by
    `place_scatter` (a 4-connected BFS subset of `open_set` reachable from the zone's
    protected web).

    User-mandated fix (2026-07-04): pocket detection must not run per zone against that
    zone's own `reach` alone — a tile absent from one zone's reach is NOT necessarily
    blocking, it may just be a NEIGHBOURING zone's open ground, and zone borders are wide
    gate bands, not walls (see `core.planning.entrances.zone_gate_bands`). Fix #1: build one GLOBAL
    reachable set (union of every zone's remaining reach) instead of a per-zone one.

    Third fix, same day (user: "there is something wrong in the way you classify open tile,
    block tile and visitable tile... The region shown is clearly not a pocket" — rejecting
    the second fix below). The second fix fed `find_pockets` the union of every zone's
    `open_set` (`global_open`). That is WRONG for geometry: `open_set` is a
    placement-eligibility layer — it also excludes approach tiles and non-blocking occupied
    cells, which ARE physically walkable. Feeding it to `find_pockets` made every such
    reserved-but-walkable tile look like a wall, fabricating a "pocket" wherever one happened
    to sit near a corner. Confirmed empirically: of 338 raw candidates found via
    `global_open`, only 116 survive once true passability is used instead — 271 (~80%) were
    false positives, including the exact mouth (11,48) example proven and sent as "fixed" in
    the prior turn. Fix: geometry now runs on `global_true` (union of every zone's
    `passable`, the tiles still walkable after vegetation and gameplay), the ACTUAL
    per-tile open/blocked layer.
    `open_set`/`global_open` still exists and still matters — but only downstream, to gate
    where a NEW object may physically land (see `global_place` below).

    Second fix, same day, superseded above but kept for the diagonal-neck rationale ("add the
    open block tile layer" — `reach` alone is still the wrong universe for pocket GEOMETRY):
    `_web_dist` is a 4-connected BFS, but `find_pockets`/`_bounded_fill` probe neighbours with
    `NB8` (H3 heroes move diagonally). A pocket whose only neck is a diagonal squeeze — or
    whose interior simply isn't 4-connected back to the web — never enters `reach` at all, so
    `find_pockets` silently skips it, neither detecting it as a pocket nor as open ground,
    even though it's physically walkable and 8-connected-reachable in-game. This diagonal
    argument is still correct; only the layer it was applied to (`global_open` instead of
    `global_true`) was wrong.

    `global_reach` (4-connected) is too narrow to gate commitment: a genuine diagonal-neck
    mouth is, by construction, passable (in `global_true`) yet absent from any zone's
    4-connected `reach`. `global_reach8` closes this: an 8-connected BFS over `global_true`,
    seeded from `global_reach`, giving the tiles a hero can ACTUALLY stand on using real H3
    movement. But standing-on and building-on are different questions — a hero can stand on
    an approach tile, yet nothing new may be placed there (it's already claimed). So actual
    commitment (guard precheck, every cache tile) gates on `global_place = global_reach8 &
    global_open`: truly reachable AND placement-eligible.

    Returns (objs, n_pockets, pocket_depth_by_tile). ``pocket_depth_by_tile`` maps every
    tile of every ACCEPTED pocket (one that passed the size/guardability gates below) to
    its normalized depth (0 = at the mouth, 1 = deepest tile) -- the one piece of pocket
    geometry a renderer needs, computed once here so nothing downstream (the debug
    overlay) has to re-derive pocket membership from placed guard objects to draw it."""
    return _PocketCachePass(catalog, zone_records, seed, bounds, context).run()


@dataclass(frozen=True, slots=True)
class _PocketPick:
    guard_tile: Tile | None
    pocket: frozenset[Tile]
    zid: int
    mouth: frozenset[Tile]
    ref_g: Tile  # ZoC-centre (reference for sorting / unguarded fallback)


@dataclass(frozen=True, slots=True)
class _PocketDraw:
    rng: random.Random
    st: TerrainStats
    pool_res: Sequence[Identity]
    pool_art: Sequence[Identity]
    pool_chest: Sequence[Identity]
    pool_vis: Sequence[Identity]


def _cache_spec(
    purpose: str, pool: Sequence[Identity] | None, ident: Identity | None = None
) -> PlaceSpec:
    return PlaceSpec(purpose, pool, ident=ident, cache=True, interactive_only=True)


@final
class _PocketCachePass:
    def __init__(
        self,
        catalog: Catalog,
        zone_records: Sequence[ZoneRecord],
        seed: int,
        bounds: tuple[int, int] | None,
        context: PocketContext,
    ) -> None:
        self.catalog = catalog
        self.seed = seed
        self.bounds = bounds
        self.border_guards = context.border_guards
        self.gameplay = context.gameplay
        self.zone_of: dict[Tile, int] = {}
        self.terrain_of: dict[int, str] = {}
        self.global_open: set[Tile] = set()
        self.global_true: set[Tile] = set()
        self.global_reach: set[Tile] = set()
        self.cover = (
            context.cover if context.cover is not None else CoverIndex(context.existing_objs)
        )
        self.pocket_depth_by_tile: dict[Tile, float] = {}
        self._sep_sq = (bounds[0] / 5.0) ** 2 if bounds else 0.0
        self._spaced: dict[
            str, list[Tile]
        ] = {}  # type -> [(x, y)] of placed instances in _POCKET_SPACED_TYPES

        for zr in zone_records:
            self._absorb(zr)
        self.global_reach8 = reach8(self.global_true, self.global_reach)
        self.global_place = self.global_reach8 & self.global_open

        # A NEW pocket guard must never cut a player's town off from its own force_town
        # mines (s2-z1 diagnosis, 2026-09) -- see home_mine_protect_pairs. `protect_blocked`
        # starts at every EXISTING non-mine guard's standing tile and grows as this function accepts
        # its own new pocket guards, so two pocket guards can't jointly seal a corridor
        # either even if neither would alone.
        protect_pairs, self.protect_blocked = home_mine_protect_pairs(
            catalog, context.existing_objs, zone_records, context.home_zids, self.global_true
        )
        self.protect_pairs = [
            (src, dst)
            for src, dst in protect_pairs
            if reachable(self.global_true, self.protect_blocked, src, dst)
        ]

        self.decor_blk = FP.decor_blocking_cells(context.existing_objs)
        precomputed = context.precomputed_pockets
        raw = precomputed if precomputed is not None else find_pockets(self.global_true)
        self.blobs = dedupe_pockets(raw, self.global_true)
        self.guard_ident = catalog.guard(1)  # mask uniform across levels 1-7; used to pre-check fit
        self.guard_mask = self.guard_ident.footprint
        self.pickup_ident = catalog.random_artifact(ART_TIER_BY_GUARD_LEVEL[0])
        self.objs: list[PlacedObject] = []
        self.guards: list[Tile] = [
            (o.x, o.y) for o in context.existing_objs if o.purpose == Purpose.GUARD
        ]

    def _absorb(self, zr: ZoneRecord) -> None:
        zid = zr.zid
        for t in zr.ts:
            self.zone_of[t] = zid
        self.terrain_of[zid] = zr.terrain
        if zr.loot_zone:
            # Include in geometry (global_true) so external tiles adjacent to the loot
            # zone see passable neighbours and don't form false pockets against its wall.
            # Exclude from open/reach so no guard or cache can be placed inside.
            self.global_true |= zr.passable
            return
        self.global_open |= zr.open_set
        self.global_true |= zr.passable
        self.global_reach |= zr.reach - self.cover.claims

    def _spaced_ok(self, typ: str | None, tx: int, ty: int) -> bool:
        """True if (tx, ty) is far enough from all prior same-type instances."""
        return (
            not self._sep_sq
            or typ is None
            or typ not in _POCKET_SPACED_TYPES
            or not any(
                (tx - px) ** 2 + (ty - py) ** 2 < self._sep_sq
                for px, py in self._spaced.get(typ, ())
            )
        )

    def _register(self, ident: Identity | None, tx: int, ty: int) -> None:
        if ident and ident.type is not None and ident.type in _POCKET_SPACED_TYPES:
            self._spaced.setdefault(ident.type, []).append((tx, ty))

    def _target(self, reach: AbstractSet[Tile], draw: _PocketDraw) -> PlaceTarget:
        return PlaceTarget(
            self.catalog, self.objs, self.cover, reach, draw.rng, draw.st, bounds=self.bounds
        )

    def _pick_spaced(
        self, pool: Sequence[Identity], t: Tile, rng: random.Random
    ) -> Identity | None:
        avail = [i for i in pool if self._spaced_ok(i.type, t[0], t[1])]
        return rng.choice(avail) if avail else (rng.choice(pool) if pool else None)

    def _fill_chest(self, target: PlaceTarget, draw: _PocketDraw, t: Tile) -> None:
        ci = self._pick_spaced(draw.pool_chest, t, draw.rng)
        if not (
            ci
            and place_one(target, _cache_spec(Purpose.REWARD_PICKUP, draw.pool_art, ci), t[0], t[1])
        ):
            _ = place_one(target, _cache_spec(Purpose.RESOURCE_PILE, draw.pool_res), t[0], t[1])
        else:
            self._register(ci, t[0], t[1])

    def _fill_visit(self, target: PlaceTarget, draw: _PocketDraw, t: Tile) -> None:
        vi = self._pick_spaced(draw.pool_vis, t, draw.rng)
        if not (vi and place_one(target, _cache_spec(Purpose.BONUS_TEMP, None, vi), t[0], t[1])):
            _ = place_one(target, _cache_spec(Purpose.RESOURCE_PILE, draw.pool_res), t[0], t[1])
        else:
            self._register(vi, t[0], t[1])

    def _pocket_fill(
        self,
        fill_spots: Sequence[Tile],
        draw: _PocketDraw,
        reach: AbstractSet[Tile] | None = None,
    ) -> None:
        """50 % resource | 25 % chest (non-artifact) | 25 % hero structure for each fill tile.

        reach: placement eligibility set — defaults to global_place (strict: open_set &
        reachable8), but pocket callers pass global_reach8 so that approach cells of
        adjacent objects (excluded from open_set but physically passable) can still
        receive pickups inside the pocket."""
        _r = reach if reach is not None else self.global_place
        target = self._target(_r, draw)
        for t in fill_spots:
            roll = draw.rng.random()
            if roll < 0.50:
                _ = place_one(target, _cache_spec(Purpose.RESOURCE_PILE, draw.pool_res), t[0], t[1])
            elif roll < 0.75:
                self._fill_chest(target, draw, t)
            else:
                self._fill_visit(target, draw, t)

    def run(self) -> tuple[list[PlacedObject], int, dict[Tile, float]]:
        for candidates in self.blobs:
            # Find the best guardable candidate (guard fits at the ZoC-centre position
            # whose ZoC seals the pocket and both mouth tiles are within it).
            pick = self._choose(candidates)
            if pick is None:
                continue
            self._fill_pocket(pick)
        return self.objs, len(self.blobs), self.pocket_depth_by_tile

    def _zone_for(self, cand_g: Tile, cand_mouth_fs: frozenset[Tile]) -> int | None:
        cand_zid = self.zone_of.get(cand_g)
        if cand_zid is None:
            for mt in sorted(cand_mouth_fs):
                cand_zid = self.zone_of.get(mt)
                if cand_zid:
                    break
        return cand_zid

    def _guard_fits(self, cand_g: Tile) -> bool:
        guard_mask = self.guard_mask
        if cand_g in self.cover.claims or not guard_spaced(cand_g, self.guards):
            return False
        if not all(
            c in self.global_place and c not in self.cover.claims
            for c in FP.interactive_cells(guard_mask, cand_g[0], cand_g[1])
        ):
            return False
        if self.protect_pairs:
            blocked = self.protect_blocked | guard_stand(guard_mask, cand_g[0], cand_g[1])
            if not all(
                reachable(self.global_true, blocked, src, dst) for src, dst in self.protect_pairs
            ):
                return False  # would seal a town off from its own starting mine
        if any(c in self.decor_blk for c in FP.interactive_cells(guard_mask, cand_g[0], cand_g[1])):
            return False
        return self.cover.accepts(PlacedObject.at(self.guard_ident, cand_g, purpose=Purpose.GUARD))

    def _pickup_fits(self, t: Tile, *covers: CoverIndex) -> bool:
        probe = PlacedObject.at(self.pickup_ident, t, purpose=Purpose.REWARD_PICKUP)
        return all(cover.accepts(probe) for cover in (self.cover, *covers))

    def _leaves_cache_spot(self, cand_g: Tile, cand_pocket: frozenset[Tile]) -> bool:
        guard_cells = {
            (x, y) for x, y, _b in FP.anchored_cells(self.guard_mask, cand_g[0], cand_g[1])
        }
        with_guard = CoverIndex([PlacedObject.at(self.guard_ident, cand_g, purpose=Purpose.GUARD)])
        return any(
            t not in self.cover.claims
            and t in self.global_place
            and t not in guard_cells
            and self._pickup_fits(t, with_guard)
            for t in cand_pocket
        )

    def _choose(
        self, candidates: Sequence[tuple[Tile, frozenset[Tile], frozenset[Tile]]]
    ) -> _PocketPick | None:
        first: _PocketPick | None = None
        fallback: _PocketPick | None = None
        for cand_g, cand_pocket, cand_mouth_fs in candidates:
            cand_zid = self._zone_for(cand_g, cand_mouth_fs)
            if cand_zid is None:
                continue
            if first is None:
                first = _PocketPick(None, cand_pocket, cand_zid, cand_mouth_fs, cand_g)
            for stand in guard_stands(cand_g, cand_pocket, cand_mouth_fs):
                if not (self._guard_fits(stand) and self._leaves_cache_spot(stand, cand_pocket)):
                    continue
                pick = _PocketPick(stand, cand_pocket, cand_zid, cand_mouth_fs, cand_g)
                if FP.overlay_clear(self.guard_mask, stand[0], stand[1], self.decor_blk):
                    return pick
                if fallback is None:
                    fallback = pick
        return fallback if fallback is not None else first

    def _fill_pocket(self, pick: _PocketPick) -> None:
        guard_tile, pocket, ref_g = pick.guard_tile, pick.pocket, pick.ref_g

        # Size gate: this is already find_pockets' own cap (POCKET_MAX_TILES) on the
        # upper end -- redundant in practice, but explicit here since it's this
        # function's actual contract with the fill logic below.
        if not (1 <= len(pocket) <= POCKET_MAX_TILES):
            return

        # Every pocket requires a guard — skip if none could be placed, unless the
        # pocket mouth is already sealed by a border guard (which isn't in global_place;
        # in that case fill proceeds without placing a new guard).
        if guard_tile is None and ref_g not in self.border_guards:
            return

        # Reference point for distance-sorting (guard tile or ZoC-centre).
        ref = guard_tile if guard_tile is not None else ref_g

        terrain = self.terrain_of[pick.zid]
        st = self.gameplay[terrain]
        pool_res = self.catalog.candidates(Purpose.RESOURCE_PILE, terrain)
        pool_art = self.catalog.candidates(Purpose.REWARD_PICKUP, terrain)
        rng = random.Random(self.seed ^ (ref_g[0] * 92821) ^ (ref_g[1] * 131071) ^ 0x9C4)
        # Pocket tiles are passable (in global_true) and reachable (in global_reach8);
        # some may be approach cells of adjacent gameplay objects (excluded from
        # open_set / global_place) -- physically walkable, but nothing NEW may be
        # placed there (2026-09 diagnosis: a cache_spot selected against the looser
        # global_reach8 while the actual `_place_one` calls below gate on the
        # stricter global_place was ALWAYS going to fail placement, yet still got
        # painted magenta by the depth-recording below -- "not all magenta tiles are
        # filled"). Select against global_place, the same set every placement call
        # below actually uses, so a selected cache_spot always CAN receive an object.
        cache_spots = [t for t in pocket if t not in self.cover.claims and t in self.global_place]
        if not cache_spots:
            return

        # Sort nearest-to-ref (index 0) → deepest (index -1).
        cache_spots.sort(key=lambda t: max(abs(t[0] - ref[0]), abs(t[1] - ref[1])))

        # Chest pool: the same explicit allow-list as loot zones (treasure chest,
        # campfire, pandora's box) -- "entirely filled with chests, pandora boxes,
        # resources, and one-tile hero-strengthening structures" (user-mandated), not
        # "everything but an artifact" (which would let scholar/corpse/spell-scroll/
        # leanTo/wagon/warriorTomb/denOfThieves leak in too).
        pool_chest = [i for i in pool_art if i.type in LOOT_CHEST_TYPES]
        pool_vis = solo_visit_pool(self.catalog, terrain, exclude_types=FILL_EXCL_TYPES)
        draw = _PocketDraw(rng, st, pool_res, pool_art, pool_chest, pool_vis)
        self._commit(pick, ref, cache_spots, draw)

    def _commit(
        self, pick: _PocketPick, ref: Tile, cache_spots: list[Tile], draw: _PocketDraw
    ) -> None:
        guard_tile = pick.guard_tile

        # Every pocket (1-10 tiles): guard at the mouth + one artifact at the deepest
        # tile, tier matching the guard's level exactly (user-mandated) -- the rest
        # (if any) filled with chests/resources/hero structures.
        n_fill = len(cache_spots) - 1  # one slot reserved for the artifact
        est_val = int(n_fill * 2.25) + 5
        lvl = min(6, 1 + (est_val >= 4) + (est_val >= 7) + (est_val >= 10) + (est_val >= 13))
        tier = ART_TIER_BY_GUARD_LEVEL[lvl - 1]

        if guard_tile is not None and not self._place_guard(guard_tile, lvl, draw):
            return

        avail = [t for t in cache_spots if t not in self.cover.claims and self._pickup_fits(t)]
        avail.sort(key=lambda t: max(abs(t[0] - ref[0]), abs(t[1] - ref[1])))
        if not avail:
            return

        self._record_depths(pick, cache_spots)

        art_spot = avail[-1:]  # deepest tile gets the artifact
        fill_spots = avail[:-1]

        # Use global_place so fill and artifact never stack on top of gameplay objects.
        self._pocket_fill(fill_spots, draw, reach=self.global_place)

        # Artifact at the deepest tile — tier matches guard level. Falls back to a
        # plain resource pile if the tiered identity doesn't land (mirrors
        # `_pocket_fill`'s own per-tile fallback): the tile was already selected via
        # `cache_spots`/`global_place`, so it CAN take something -- it must not stay
        # empty under the tile it was recorded as pocket depth for.
        if art_spot:
            self._place_artifact(art_spot[0], self.catalog.random_artifact(tier), draw)

    def _place_guard(self, guard_tile: Tile, lvl: int, draw: _PocketDraw) -> bool:
        gident = self.catalog.guard(lvl)
        if not place_one(
            self._target(self.global_place, draw),
            PlaceSpec(Purpose.GUARD, None, ident=gident, interactive_only=True),
            guard_tile[0],
            guard_tile[1],
        ):
            return False
        self.objs[-1].pocket_guard = True
        self.guards.append(guard_tile)
        if self.protect_pairs:
            self.protect_blocked |= guard_stand(self.guard_mask, guard_tile[0], guard_tile[1])
        return True

    def _place_artifact(self, t: Tile, ident: Identity, draw: _PocketDraw) -> None:
        target = self._target(self.global_place, draw)
        art = _cache_spec(Purpose.REWARD_PICKUP, draw.pool_art, ident)
        if not place_one(target, art, t[0], t[1]):
            _ = place_one(target, _cache_spec(Purpose.RESOURCE_PILE, draw.pool_res), t[0], t[1])

    def _record_depths(self, pick: _PocketPick, cache_spots: list[Tile]) -> None:
        pocket = pick.pocket
        # This pocket is genuinely committed now -- a guard is down (or the mouth was
        # already border-sealed) and at least one cache tile is actually going to
        # receive an object below. Only NOW record its geometric extent + depth
        # gradient for the debug overlay (rendering only; it never re-derives this from
        # objects) -- recording it any earlier (right after the guard-required gate)
        # painted a pocket magenta even when every later gate (`cache_spots`/`avail`
        # empty, guard placement itself failing) still dropped it with zero objects
        # actually placed (2026-09 diagnosis: "not all magenta tiles are filled").
        #
        # Restrict WHICH tiles get recorded to `fillable`: every selected cache_spot
        # (will receive an object below, or already got the guard) plus any pocket
        # tile some earlier pass already claimed. A pocket tile that is neither -- e.g.
        # an approach cell of an adjacent object, walkable but off-limits to new
        # placements -- is not a real fillable part of this pocket; painting it magenta
        # would repeat the same "empty tile with nothing underneath" bug one tile at a
        # time instead of one whole pocket at a time.
        fillable = set(cache_spots) | (pocket & self.cover.claims)
        depths = pocket_depths(pocket, pick.mouth)
        max_d = max(depths.values()) if depths else 0
        for t, d in depths.items():
            if t not in fillable:
                continue
            self.pocket_depth_by_tile[t] = d / max_d if max_d else 0.0

"""Guarded pocket caches + Seer Hut quests — Repair-only (always ran from
`_repair_and_finish_level`, never from `_run_level`'s per-zone passes).
"""

import collections
import random
from collections.abc import Collection, Container, Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from itertools import pairwise
from typing import final

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.geometry import NB8
from vcmi_mapgen.core.grid.pockets import POCKET_MAX_TILES, find_pockets, mouth_key, pocket_depths
from vcmi_mapgen.core.model import (
    CoverIndex,
    Footprint,
    Identity,
    JsonValue,
    PlacedObject,
    Tile,
    ZoneRecord,
)
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.resource import Resource
from vcmi_mapgen.core.steps.gameplay.mines import TerrainStats, load_gameplay
from vcmi_mapgen.core.steps.gate.gates import rnd_monster
from vcmi_mapgen.core.steps.placement import (
    PANDORA_CREATURES,
    RW_LIMITER,
    RW_REWARD,
    RW_TEXT,
    PlaceSpec,
    PlaceTarget,
    guard_spaced,
    place_one,
)
from vcmi_mapgen.core.steps.treasure.fill import (
    FILL_EXCL_ANIMS,
    LOOT_CHEST_TYPES,
    solo_visit_pool,
)
from vcmi_mapgen.kit import objects as OR

# Artifact tier (animation name from RND_ART) indexed by monster level 1-6:
# treasure(1-2) → minor(3) → major(4-5) → any/relic(6).
# The monster level is derived from resources + visitable structures placed in the pocket;
# the artifact at the deepest tile then matches that level so the guard's strength is
# always proportional to the prize behind it.
ART_BY_LVL = ["avarnd1", "avarnd1", "avarnd2", "avarnd3", "avarnd3", "avarand"]

# Types that must maintain a minimum map-fraction separation between any two instances in pockets.
_POCKET_SPACED_TYPES = frozenset({"magicWell", "warriorTomb"})


def _guard_stand(mask: Footprint, x: int, y: int) -> set[Tile]:
    return set(OR.interactive_cells(mask, x, y))


def _approach_tiles(mask: Footprint, x: int, y: int, passable: Container[Tile]) -> set[Tile]:
    """Passable tiles a hero could stand on to visit this object -- its own interactive
    cell(s) when walk-on, plus every passable 8-neighbour of them (covers a
    blocked-entrance 'X' interactive cell, which is clicked from an adjacent tile, never
    stood on itself)."""
    ap: set[Tile] = set()
    for ix, iy in OR.interactive_cells(mask, x, y):
        if (ix, iy) in passable:
            ap.add((ix, iy))
        for dx, dy in NB8:
            nb = (ix + dx, iy + dy)
            if nb in passable:
                ap.add(nb)
    return ap


def _reachable(
    passable: AbstractSet[Tile],
    blocked: AbstractSet[Tile],
    sources: AbstractSet[Tile],
    targets: AbstractSet[Tile],
) -> bool:
    """8-connected BFS: can a hero reach any `targets` tile from `sources` while never
    stepping into `blocked`? `sources`/`targets` themselves are always allowed (they are
    the actual endpoints, not obstacles)."""
    avail = (passable - blocked) | sources | targets
    frontier = collections.deque(t for t in sources if t in avail)
    seen = set(frontier)
    while frontier:
        x, y = frontier.popleft()
        if (x, y) in targets:
            return True
        for dx, dy in NB8:
            nb = (x + dx, y + dy)
            if nb in avail and nb not in seen:
                seen.add(nb)
                frontier.append(nb)
    return bool(seen & targets)


def home_mine_protect_pairs(
    existing_objs: Sequence[PlacedObject],
    zone_records: Sequence[ZoneRecord],
    home_zids: Collection[int],
    global_true: Container[Tile],
) -> tuple[list[tuple[frozenset[Tile], frozenset[Tile]]], set[Tile]]:
    """(town_approach, mine_approach) pairs that a NEW pocket guard must never sever --
    one pair per force_town zone's own sawmill/orePit (`home_zids`), for every player
    town on this level (s2-z1 diagnosis, 2026-09: a pocket guard placed right by the
    castle sealed the only route to BOTH of its own starting mines, even though each
    already carries its own dedicated level-1 guard -- a mine's day-1 economy must stay
    reachable without an extra, involuntary fight). Also returns the standing tile of
    every EXISTING guard that is not itself a mine's own guard (those are expected
    fights, never a blocker) -- the base 'blocked' set the caller folds new pocket guards
    into as they're accepted. Returns (protect_pairs, base_blocked)."""
    if not home_zids:
        return [], set()
    ts_by_zid = {zr.zid: zr.ts for zr in zone_records}
    mine_cells = _mine_cells(existing_objs)
    base_blocked = _base_blocked(existing_objs, mine_cells)

    pairs: list[tuple[frozenset[Tile], frozenset[Tile]]] = []
    for zid in home_zids:
        ts = ts_by_zid.get(zid)
        if ts is None:
            continue
        pairs.extend(_home_zone_pairs(existing_objs, ts, global_true))
    return pairs, base_blocked


def _mine_cells(existing_objs: Sequence[PlacedObject]) -> set[Tile]:
    mine_cells: set[Tile] = set()
    for o in existing_objs:
        if o.purpose == Purpose.MINE:
            mask = o.footprint
            if mask.cells:
                mine_cells |= {(cx, cy) for cx, cy, _b in OR.anchored_cells(mask, o.x, o.y)}
    return mine_cells


def _is_mine_guard(o: PlacedObject, mine_cells: Iterable[Tile]) -> bool:
    return any(max(abs(o.x - mx), abs(o.y - my)) <= 1 for mx, my in mine_cells)


def _base_blocked(existing_objs: Sequence[PlacedObject], mine_cells: set[Tile]) -> set[Tile]:
    base_blocked: set[Tile] = set()
    for o in existing_objs:
        if o.purpose == Purpose.GUARD and not _is_mine_guard(o, mine_cells):
            mask = o.footprint
            if mask.cells:
                base_blocked |= _guard_stand(mask, o.x, o.y)
    return base_blocked


def _home_zone_pairs(
    existing_objs: Sequence[PlacedObject], ts: AbstractSet[Tile], global_true: Container[Tile]
) -> list[tuple[frozenset[Tile], frozenset[Tile]]]:
    pairs: list[tuple[frozenset[Tile], frozenset[Tile]]] = []
    town = next(
        (o for o in existing_objs if o.purpose == Purpose.TOWN and (o.x, o.y) in ts),
        None,
    )
    if town is None:
        return pairs
    town_ap = _approach_tiles(town.footprint, town.x, town.y, global_true)
    if not town_ap:
        return pairs
    for o in existing_objs:
        if not (
            o.purpose == Purpose.MINE and o.subtype in ("sawmill", "orePit") and (o.x, o.y) in ts
        ):
            continue
        mine_ap = _approach_tiles(o.footprint, o.x, o.y, global_true)
        if mine_ap:
            pairs.append((frozenset(town_ap), frozenset(mine_ap)))
    return pairs


def _reach8(open_set: Container[Tile], seed: Iterable[Tile]) -> set[Tile]:
    """8-connected BFS over the true `open_set` (the physical open/blocked tile layer),
    seeded from tiles already proven reachable by `_web_dist`. Extends that 4-connected web
    reach with anything only joined by a diagonal step — H3 heroes move diagonally, so a
    tile behind a corner-cut squeeze IS reachable in play even though `_web_dist` can't see
    past it. This is the layer pocket mouths/cache tiles are actually validated against:
    plain `open_set` membership alone would also accept ground that is open but totally
    disconnected from the web (an unreachable floating island), which is not placeable
    either."""
    d = set(t for t in seed if t in open_set)
    q = collections.deque(d)
    while q:
        x, y = q.popleft()
        for dx, dy in NB8:
            n = (x + dx, y + dy)
            if n in open_set and n not in d:
                d.add(n)
                q.append(n)
    return d


def dedupe_pockets(
    pockets: Mapping[Tile, tuple[frozenset[Tile], frozenset[Tile]]],
    reach: Container[Tile] = (),
) -> list[list[tuple[Tile, frozenset[Tile], frozenset[Tile]]]]:
    """Collapse near-duplicate mouth candidates into one CANDIDATE LIST per genuine physical
    nook. `find_pockets` returns one entry per candidate MOUTH tile, but several nearby
    tiles each independently qualify as "the" guard spot of the same nook (a ZoC-neck is 3x3,
    so a flat-face nook alone yields ~4 candidates) -- and in H3 a guard already threatens
    every adjacent tile (stepping next to a wandering monster forces combat), so one guard
    placed at a shared neck already gates every mouth candidate touching it. Merge
    guard_tile+pocket tiles into 4-connected blobs (union-find over shared tiles).

    `pockets` maps guard_tile -> (pocket_frozenset, mouth_frozenset) as returned by
    `find_pockets`.

    Returns a list of candidate lists (one list per nook), each sorted by `mouth_key`
    over `reach` (in-neck first, then largest pocket, then orthogonal-front), outer list
    sorted best-top-candidate first. Each candidate is a (guard_tile, pocket, mouth_fs)
    triple. The caller tries candidates within a blob in order and falls back to the next
    one when the top pick's mouth tile is unusable."""
    items = [(g, pocket, mouth_fs) for g, (pocket, mouth_fs) in pockets.items()]
    owner: collections.defaultdict[Tile, list[int]] = collections.defaultdict(list)
    for idx, (g, pocket, _mouth_fs) in enumerate(items):
        for t in (g, *pocket):
            owner[t].append(idx)
    parent = list(range(len(items)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for idxs in owner.values():
        for a, b in pairwise(idxs):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

    groups: collections.defaultdict[int, list[tuple[Tile, frozenset[Tile], frozenset[Tile]]]] = (
        collections.defaultdict(list)
    )
    for idx, (g, pocket, mouth_fs) in enumerate(items):
        groups[find(idx)].append((g, pocket, mouth_fs))
    blobs = [
        sorted(cands, key=lambda kv: mouth_key(reach, kv[0], kv[1])) for cands in groups.values()
    ]
    return sorted(blobs, key=lambda cands: mouth_key(reach, cands[0][0], cands[0][1]))


def _seerhut_reward(rng: random.Random) -> dict[str, JsonValue]:
    """The seer hut's own `options.rewardable` payout, paid once its quest's artifact
    condition is met -- same flavour draw as `_pandora_reward` but a tier up (VCMI's own
    RMG seer-hut samples pay in the 5-figure XP / dozens-of-creatures range, well above
    pandora's open-scatter tier: a seer hut costs the hero a whole side-quest, not a
    five-second detour)."""
    reward = dict(RW_REWARD)
    flavor = rng.choices(("gold", "experience", "creatures"), weights=(35, 40, 25), k=1)[0]
    if flavor == "gold":
        reward["resources"] = {Resource.GOLD: rng.choice((3000, 5000, 7500, 10000, 15000))}
    elif flavor == "experience":
        reward["heroExperience"] = rng.choice((2500, 5000, 7500, 10000, 15000))
    else:
        reward["creatures"] = [
            {"type": f"core:{rng.choice(PANDORA_CREATURES)}", "amount": rng.randint(5, 20)}
        ]
    return reward


def _seerhut_quest(rng: random.Random, artifact_subtype: str) -> dict[str, JsonValue]:
    """VCMI 'Quest' + 'Rewardable' payload for a seerHut (schema captured verbatim from two
    real VCMI-RMG .vmap seerHut instances): a MISSION_ARTIFACT quest -- the hero must be
    CARRYING one specific named artifact -- gated via `quest.limiter.artifacts`. The sibling
    `rewardable.info[]` entry (paid out once the quest is satisfied) keeps the plain no-op
    base limiter: the artifact CHECK lives only in `quest.limiter`, confirmed against both
    reference instances, whose own `rewardable` limiter carries no `artifacts` restriction of
    its own."""
    quest_limiter: dict[str, JsonValue] = {
        **RW_LIMITER,
        "artifacts": [f"core:{artifact_subtype}"],
    }
    return {
        "quest": {
            "completedText": dict(RW_TEXT),
            "firstVisitText": dict(RW_TEXT),
            "limiter": quest_limiter,
            "nextVisitText": dict(RW_TEXT),
        },
        "rewardable": {
            "info": [
                {
                    "limiter": dict(RW_LIMITER),
                    "message": dict(RW_TEXT),
                    "reward": _seerhut_reward(rng),
                    "visitType": 1,
                }
            ],
            "infoWindowType": 0,
            "onSelect": dict(RW_TEXT),
            "resetParameters": {"period": 0},
            "selectMode": "selectFirst",
            "visitMode": "unlimited",
        },
    }


@dataclass(frozen=True, slots=True)
class PocketContext:
    border_guards: Container[Tile] = ()
    precomputed_pockets: Mapping[Tile, tuple[frozenset[Tile], frozenset[Tile]]] | None = None
    existing_objs: Sequence[PlacedObject] = ()
    home_zids: Collection[int] = ()


_DEFAULT_POCKET_CONTEXT = PocketContext()


def place_pocket_caches(
    catalog: Catalog,
    zone_records: Sequence[ZoneRecord],
    seed: int = 1,
    bounds: tuple[int, int] | None = None,
    context: PocketContext = _DEFAULT_POCKET_CONTEXT,
) -> tuple[list[PlacedObject], int, dict[Tile, float]]:
    """Guarded caches in genuine geometric pockets — found in ONE global, zone-independent
    pass over the WHOLE map's TRUE physical passability, run once after every zone's
    terrain, vegetation and scatter is finalized. `zone_records` is a list of
    {"zid", "terrain", "ts", "open_set", "passable", "reach", "used"}: `open_set` is that
    zone's PLACEMENT-ELIGIBLE tiles (terrain minus vegetation-blocked/gameplay-occupied/
    approach cells — nothing new may stack there); `passable` is that zone's TRUE physical
    passability (terrain minus only the tiles that are actually impassable — approach tiles
    and non-blocking occupied footprint cells stay in it, since a hero can walk over them
    even though nothing new can be placed there); `reach`/`used` as returned by
    `place_scatter` (a 4-connected BFS subset of `open_set` reachable from the zone's
    protected web).

    User-mandated fix (2026-07-04): pocket detection must not run per zone against that
    zone's own `reach` alone — a tile absent from one zone's reach is NOT necessarily
    blocking, it may just be a NEIGHBOURING zone's open ground, and zone borders are wide
    gate bands, not walls (see `kit.topology.zone_gate_bands`). Fix #1: build one GLOBAL
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
    `passable`, i.e. `ts - blocked - gblocked`), the ACTUAL per-tile open/blocked layer.
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


def _guard_stands(g: Tile, pocket: frozenset[Tile], mouth: frozenset[Tile]) -> list[Tile]:
    xs = [t[0] for t in mouth]
    ys = [t[1] for t in mouth]
    ring = [
        (x, y)
        for x in range(max(xs) - 1, min(xs) + 2)
        for y in range(max(ys) - 1, min(ys) + 2)
        if (x, y) not in pocket and (x, y) not in mouth
    ]
    ring.sort(key=lambda t: (min(abs(t[0] - m[0]) + abs(t[1] - m[1]) for m in mouth), t))
    return [g, *sorted(mouth - {g}), *ring]


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
        self.zone_of: dict[Tile, int] = {}
        self.terrain_of: dict[int, str] = {}
        self.global_open: set[Tile] = set()
        self.global_true: set[Tile] = set()
        self.global_reach: set[Tile] = set()
        self.used: set[Tile] = set()
        self.pocket_depth_by_tile: dict[Tile, float] = {}
        self._sep_sq = (bounds[0] / 5.0) ** 2 if bounds else 0.0
        self._spaced: dict[
            str, list[Tile]
        ] = {}  # type -> [(x, y)] of placed instances in _POCKET_SPACED_TYPES

        for zr in zone_records:
            self._absorb(zr)
        self.global_reach8 = _reach8(self.global_true, self.global_reach)
        self.global_place = self.global_reach8 & self.global_open

        # A NEW pocket guard must never cut a player's town off from its own force_town
        # mines (s2-z1 diagnosis, 2026-09) -- see home_mine_protect_pairs. `protect_blocked`
        # starts at every EXISTING non-mine guard's standing tile and grows as this function accepts
        # its own new pocket guards, so two pocket guards can't jointly seal a corridor
        # either even if neither would alone.
        protect_pairs, self.protect_blocked = home_mine_protect_pairs(
            context.existing_objs, zone_records, context.home_zids, self.global_true
        )
        self.protect_pairs = [
            (src, dst)
            for src, dst in protect_pairs
            if _reachable(self.global_true, self.protect_blocked, src, dst)
        ]

        self.decor_blk = OR.decor_blocking_cells(context.existing_objs)
        precomputed = context.precomputed_pockets
        raw = precomputed if precomputed is not None else find_pockets(self.global_true)
        self.blobs = dedupe_pockets(raw, self.global_true)
        self.guard_ident = rnd_monster(
            catalog, 1
        )  # mask uniform across levels 1-7; used to pre-check fit
        self.guard_mask = self.guard_ident.footprint
        self.pickup_ident = catalog.identity_of(ART_BY_LVL[0])
        self.objs: list[PlacedObject] = []
        self.cover = CoverIndex(context.existing_objs)
        self.guards: list[Tile] = [
            (o.x, o.y) for o in context.existing_objs if o.purpose == Purpose.GUARD
        ]

    def _absorb(self, zr: ZoneRecord) -> None:
        zid = zr.zid
        for t in zr.ts:
            self.zone_of[t] = zid
        self.terrain_of[zid] = zr.terrain
        self.used |= zr.used  # always claim used cells — no double-stacking
        if zr.loot_zone:
            # Include in geometry (global_true) so external tiles adjacent to the loot
            # zone see passable neighbours and don't form false pockets against its wall.
            # Exclude from open/reach so no guard or cache can be placed inside.
            self.global_true |= zr.passable
            return
        self.global_open |= zr.open_set
        self.global_true |= zr.passable
        self.global_reach |= zr.reach - zr.used

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
            self.catalog,
            self.objs,
            self.used,
            reach,
            draw.rng,
            draw.st,
            bounds=self.bounds,
            cover=self.cover,
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
        if cand_g in self.used or not guard_spaced(cand_g, self.guards):
            return False
        if not all(
            c in self.global_place and c not in self.used
            for c in OR.interactive_cells(guard_mask, cand_g[0], cand_g[1])
        ):
            return False
        if self.protect_pairs:
            blocked = self.protect_blocked | _guard_stand(guard_mask, cand_g[0], cand_g[1])
            if not all(
                _reachable(self.global_true, blocked, src, dst) for src, dst in self.protect_pairs
            ):
                return False  # would seal a town off from its own starting mine
        if any(c in self.decor_blk for c in OR.interactive_cells(guard_mask, cand_g[0], cand_g[1])):
            return False
        return self.cover.accepts(PlacedObject.at(self.guard_ident, cand_g, purpose=Purpose.GUARD))

    def _pickup_fits(self, t: Tile, *covers: CoverIndex) -> bool:
        probe = PlacedObject.at(self.pickup_ident, t, purpose=Purpose.REWARD_PICKUP)
        return all(cover.accepts(probe) for cover in (self.cover, *covers))

    def _leaves_cache_spot(self, cand_g: Tile, cand_pocket: frozenset[Tile]) -> bool:
        guard_cells = {
            (x, y) for x, y, _b in OR.anchored_cells(self.guard_mask, cand_g[0], cand_g[1])
        }
        with_guard = CoverIndex([PlacedObject.at(self.guard_ident, cand_g, purpose=Purpose.GUARD)])
        return any(
            t not in self.used
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
            for stand in _guard_stands(cand_g, cand_pocket, cand_mouth_fs):
                if not (self._guard_fits(stand) and self._leaves_cache_spot(stand, cand_pocket)):
                    continue
                pick = _PocketPick(stand, cand_pocket, cand_zid, cand_mouth_fs, cand_g)
                if OR.overlay_clear(self.guard_mask, stand[0], stand[1], self.decor_blk):
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
        st = load_gameplay()[terrain]
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
        cache_spots = [t for t in pocket if t not in self.used and t in self.global_place]
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
        pool_vis = solo_visit_pool(self.catalog, terrain, exclude_anims=FILL_EXCL_ANIMS)
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
        anim = ART_BY_LVL[lvl - 1]

        if guard_tile is not None and not self._place_guard(guard_tile, lvl, draw):
            return

        avail = [t for t in cache_spots if t not in self.used and self._pickup_fits(t)]
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
            self._place_artifact(art_spot[0], anim, draw)

    def _place_guard(self, guard_tile: Tile, lvl: int, draw: _PocketDraw) -> bool:
        gident = rnd_monster(self.catalog, lvl)
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
            self.protect_blocked |= _guard_stand(self.guard_mask, guard_tile[0], guard_tile[1])
        return True

    def _place_artifact(self, t: Tile, anim: str, draw: _PocketDraw) -> None:
        target = self._target(self.global_place, draw)
        art = _cache_spec(Purpose.REWARD_PICKUP, draw.pool_art, self.catalog.identity_of(anim))
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
        fillable = set(cache_spots) | (pocket & self.used)
        depths = pocket_depths(pocket, pick.mouth)
        max_d = max(depths.values()) if depths else 0
        for t, d in depths.items():
            if t not in fillable:
                continue
            self.pocket_depth_by_tile[t] = d / max_d if max_d else 0.0


SEERHUT_ZONE_RATIO = 4  # ~1 seer-hut quest per 4 eligible zones -- zone_engine.py's own
# corpus-replay convention for the same object
MAX_SEER_HUTS = 6
SEERHUT_MIN_REACH = 8  # a zone needs at least this many free reachable tiles to be worth
# drawing into a quest (host EITHER the hut or its artifact)


@dataclass(frozen=True, slots=True)
class SeerHutContext:
    pocket_tiles: AbstractSet[Tile] | None = None
    existing_objs: Sequence[PlacedObject] = ()
    used_artifacts: set[str] | None = None


_DEFAULT_SEERHUT_CONTEXT = SeerHutContext()


@dataclass(frozen=True, slots=True)
class _QuestEnv:
    catalog: Catalog
    eligible: Sequence[ZoneRecord]
    ptiles: AbstractSet[Tile]
    used_artifacts: set[str]
    objs: list[PlacedObject]
    bounds: tuple[int, int] | None
    cover: CoverIndex


def place_seer_hut_quests(
    catalog: Catalog,
    zone_records: Sequence[ZoneRecord],
    seed: int = 1,
    bounds: tuple[int, int] | None = None,
    context: SeerHutContext = _DEFAULT_SEERHUT_CONTEXT,
) -> tuple[list[PlacedObject], int]:
    """One or more Seer Hut quests for the WHOLE level (VCMI RMG convention: a seer hut's
    mission gates on a single named artifact the hero must find and hand-carry to it). Each
    quest links two placements in DIFFERENT zones -- the quest's target artifact (an
    unguarded findable pickup, same "always free in open ground" doctrine as scatter loot --
    see the module docstring) and the seer hut itself (a rigid visitable building) -- with the
    hut's `options.quest.limiter.artifacts` naming the exact artifact identity placed for it.

    Runs once per level, after every zone's own gameplay/vegetation/scatter is finalized and
    the map-level G2/island repair has run (so both placements land on truly reachable
    ground), and BEFORE the pocket-cache pass claims the remaining nooks -- `zone_records`'
    `open_set`/`reach`/`used` are shared with that pass, so tiles this function spends are
    already excluded when pockets are judged.

    `context.used_artifacts`, when passed, is a set MUTATED in place and shared across every level's
    call for the same map (see `pp_map.build`) -- a named artifact is a map-unique relic in
    vanilla H3, so one quest's target must never double as another level's target too.

    `zone_records` is a list of {"zid", "terrain", "ts", "open_set", "passable", "reach",
    "used"} (see `pp_map._run_level`/`place_pocket_caches`). Returns (objs, n_quests)."""
    eligible = [zr for zr in zone_records if len(zr.reach - zr.used) >= SEERHUT_MIN_REACH]
    if len(eligible) < 2:
        return [], 0
    n = min(MAX_SEER_HUTS, max(1, len(eligible) // SEERHUT_ZONE_RATIO))

    rng_pair = random.Random(seed ^ 0xEE47)
    objs: list[PlacedObject] = []
    cover = CoverIndex(context.existing_objs)
    used_artifacts = context.used_artifacts if context.used_artifacts is not None else set[str]()
    placed = 0
    # Pre-compute which zones have pocket tiles so the per-attempt loop can skip quickly.
    _ptiles_global = _quest_pocket_tiles(zone_records, context.pocket_tiles)
    env = _QuestEnv(catalog, eligible, _ptiles_global, used_artifacts, objs, bounds, cover)

    for i in range(n):
        idx_hut, idx_art = rng_pair.sample(range(len(eligible)), 2)
        rng = random.Random(seed ^ (i * 92821) ^ 0xEE47)
        if _place_quest(env, rng, idx_hut, idx_art):
            placed += 1
    return objs, placed


def _quest_pocket_tiles(
    zone_records: Sequence[ZoneRecord], pocket_tiles: AbstractSet[Tile] | None
) -> AbstractSet[Tile]:
    if pocket_tiles is not None:
        return pocket_tiles
    passable_all = set[Tile]().union(*(zr.passable for zr in zone_records))
    raw_p = find_pockets(passable_all)
    _ptiles_acc: set[Tile] = set()
    for _g, (pt, _mf) in raw_p.items():
        if len(pt) >= 3:
            _ptiles_acc |= set(pt)
    return _ptiles_acc


def _place_quest(env: _QuestEnv, rng: random.Random, idx_hut: int, idx_art: int) -> bool:
    eligible = env.eligible
    hut_zr = eligible[idx_hut]

    pool_hut = sorted(
        (
            h
            for h in env.catalog.candidates(Purpose.QUEST_GATE, hut_zr.terrain)
            if h.type == "seerHut"
        ),
        key=lambda h: h.animation,
    )
    if not pool_hut:
        return False
    hut_ident = rng.choice(pool_hut)

    # Find an art zone with a ≥3-tile pocket; start with the random pick then
    # try other eligible zones to avoid getting 0 quests when the chosen zone
    # has no pocket tiles available.
    art_zr_order = [eligible[idx_art]] + [
        zr for j, zr in enumerate(eligible) if j not in (idx_art, idx_hut)
    ]
    art_zr, art_ident = _pick_art_zone(env, rng, art_zr_order)
    if art_zr is None or art_ident is None or art_ident.subtype is None:
        return False  # no eligible art zone with a ≥3-tile pocket

    art_xy = _place_art(env, rng, art_zr, art_ident)
    if art_xy is None:
        return False

    if not _place_hut(env, rng, hut_zr, hut_ident, art_ident.subtype):
        # no room for the hut => a dangling quest artifact nobody asked for; drop it
        # rather than leave an orphaned reference
        _ = env.objs.pop()
        for cx, cy, _b in OR.anchored_cells(art_ident.footprint, art_xy[0], art_xy[1]):
            art_zr.used.discard((cx, cy))
        return False

    env.used_artifacts.add(art_ident.subtype)
    return True


def _pick_art_zone(
    env: _QuestEnv, rng: random.Random, art_zr_order: Sequence[ZoneRecord]
) -> tuple[ZoneRecord, Identity] | tuple[None, None]:
    for cand_art_zr in art_zr_order:
        art_eligible = env.ptiles & (cand_art_zr.reach - cand_art_zr.used)
        if not art_eligible:
            continue
        cand_pool_art = sorted(
            (
                a
                for a in env.catalog.candidates(Purpose.REWARD_PICKUP, cand_art_zr.terrain)
                if a.type == "artifact" and a.subtype not in env.used_artifacts
            ),
            key=lambda a: a.animation,
        )
        if not cand_pool_art:
            continue
        return cand_art_zr, rng.choice(cand_pool_art)
    return None, None


def _place_art(
    env: _QuestEnv, rng: random.Random, art_zr: ZoneRecord, art_ident: Identity
) -> Tile | None:
    st_art = load_gameplay()[art_zr.terrain]
    art_eligible = env.ptiles & (art_zr.reach - art_zr.used)
    art_cands = sorted(art_eligible)
    rng.shuffle(art_cands)
    target = PlaceTarget(
        env.catalog,
        env.objs,
        art_zr.used,
        art_zr.reach,
        rng,
        st_art,
        bounds=env.bounds,
        cover=env.cover,
    )
    spec = PlaceSpec(Purpose.REWARD_PICKUP, None, ident=art_ident)
    for t in art_cands:
        if place_one(target, spec, t[0], t[1]):
            return t
    return None


def _place_hut(
    env: _QuestEnv, rng: random.Random, hut_zr: ZoneRecord, hut_ident: Identity, art_subtype: str
) -> bool:
    st_hut = load_gameplay()[hut_zr.terrain]
    hut_cands = sorted(hut_zr.reach - hut_zr.used)
    rng.shuffle(hut_cands)
    options = _seerhut_quest(rng, art_subtype)
    target = PlaceTarget(
        env.catalog,
        env.objs,
        hut_zr.used,
        hut_zr.reach,
        rng,
        st_hut,
        bounds=env.bounds,
        cover=env.cover,
    )
    spec = PlaceSpec(Purpose.QUEST_GATE, None, ident=hut_ident, options=options)
    return any(place_one(target, spec, t[0], t[1]) for t in hut_cands)

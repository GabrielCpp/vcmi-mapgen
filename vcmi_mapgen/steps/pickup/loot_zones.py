"""Loot-zone access mechanic (gate+keymaster / sealed+monolith) for small single-entrance
zones — a global, per-level pass that runs once every zone's scatter is placed.

Also owns `solo_visit_pool`/`shrine_spell_level`, needed by
`steps.loot.caches.place_pocket_caches` too — Pickup is the first step in pipeline order
to need them.
"""

import collections
import random
import re
from collections.abc import Collection, Iterable, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from operator import itemgetter
from typing import Self, final

from vcmi_mapgen import ontology as ON
from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.models import CoverIndex, Identity, PlacedObject, Tile, ZoneRecord
from vcmi_mapgen.steps.gameplay import mines as PG
from vcmi_mapgen.steps.gameplay.water import CellRules, legal_cells
from vcmi_mapgen.steps.gate.gates import rnd_monster
from vcmi_mapgen.steps.pickup.scatter import PlaceSpec, PlaceTarget, place_one

LOOT_ZONE_MAX_TILES = 60  # land zone with ≤ this many tiles, exactly one entrance cluster, no town

_LOOT_COLORS = [  # (border_gate_anim, keymaster_anim); index == VCMI subtype 0-7
    ("avxbgt00", "avxkey00"),  # 0 light blue
    ("avxbgt10", "avxkey10"),  # 1 green
    ("avxbgt20", "avxkey20"),  # 2 red
    ("avxbgt30", "avxkey30"),  # 3 dark blue
    ("avxbgt40", "avxkey40"),  # 4 brown
    ("avxbgt50", "avxkey50"),  # 5 purple
    ("avxbgt60", "avxkey60"),  # 6 white
    ("avxbgt70", "avxkey70"),  # 7 black
]
_LOOT_ART_W = {"avarnd1": 5, "avarnd2": 15, "avarnd3": 35, "avarnd4": 45}
_LOOT_EXCL_DECOR = frozenset({"LAKE", "FROZEN_LAKE", "RIVER_DELTA", "KELP", "REEF", "LAKE_2"})
# Visitable structures excluded from pocket caches (steps.loot.caches still uses this).
FILL_EXCL_ANIMS = frozenset({"avsfntn0", "avsidol0"})  # Fountain of Fortune, Idol of Fortune
# REWARD_PICKUP types excluded from loot zone art/chest fill (pool_art + pool_chest).
_LOOT_ART_EXCL_TYPES = frozenset({"leanTo", "wagon", "warriorTomb", "denOfThieves"})
# chest-type fill is an explicit allow-list, not "everything but an artifact": scholar,
# corpse and a spell scroll are REWARD_PICKUP too but are not a chest and were never meant
# to be loot-zone content. Shared with steps.loot.caches' pocket fill -- don't widen
# this one for loot-zone-only needs (see _LOOT_ZONE_CHEST_EXTRA_TYPES below instead).
LOOT_CHEST_TYPES = ("treasureChest", "campfire", "pandoraBox")
# Loot-zone-only chest-tier additions on top of LOOT_CHEST_TYPES (user-mandated
# 2026-09) -- NOT added to LOOT_CHEST_TYPES itself since pocket fill (caches.py) reuses
# that constant and wasn't asked to change. Spell scrolls are handled separately (a
# fixed level 4-5 spell, not the plain unconfigured-random pool entry) -- see
# _fill_loot's Pass 2.
_LOOT_ZONE_CHEST_EXTRA_TYPES = ("scholar",)
# A loot-zone spell scroll is always a real, fixed level 4 or 5 spell (never the
# unconfigured-random pool entry) -- see ontology.spells_by_level, hand-extracted from
# H3's own SPTRAITS.TXT (data/spell_levels.json).
_LOOT_SCROLL_LEVELS = (4, 5)
# Hero-strengthening structures allowed in loot-zone fill (Pass 1) -- an explicit
# allow-list (user-mandated 2026-09), not "every solo-visitable object": these are all
# STAT_PERMANENT. Exactly TWO of each type get placed per zone, apart from each other
# (never adjacent) -- see _fill_loot's Pass 1.
_LOOT_HERO_STRUCTURE_TYPES = frozenset(
    {
        "learningStone",
        "gardenOfRevelation",
        "starAxis",
    }
)
_LOOT_HERO_STRUCTURE_COUNT = 2  # instances of EACH whitelisted type placed per zone
LOOT_HERO_STRUCTURE_MIN_SEP = 2  # Chebyshev distance the two instances of one type
# must clear -- "separated... not adjacent" (user-mandated)
# Rare resources allowed in a loot zone: mercury, sulfur, crystal, gems, gold -- no wood/ore
# (colloquially "stone") and no unrestricted randomResource (could resolve to either).
_LOOT_RARE_RESOURCE_SUBTYPES = frozenset({"mercury", "sulfur", "crystal", "gems", "gold"})
# Two-way monolith pairs for sealed teleport loot zones (ci > 0).
# Both ends of each pair use the SAME animation → same subtype → they teleport to each other.
# Subtypes monolith1-4 (simple 1-4 cell, no blocking body) suit small pockets best.
_LOOT_MONOLITHS = ["avxmn2g0", "avxmn2o0", "avxmn2p0", "avxmn4b0"]

_SOLO_VIS_PURPOSES = ("BONUS_TEMP", "SPELL_SKILL", "MANA", "STAT_PERMANENT")

_DIRS8 = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]


def _find_entry_tile(
    interactive: Collection[Tile],
    footprint_cells: Sequence[tuple[int, int, bool]],
    ts: AbstractSet[Tile],
) -> Tile | None:
    """The tile just beyond the access object that must stay forever passable and
    unclaimed -- the doorway the hero actually steps onto once the gate opens or
    the monolith is reached. A direct neighbour of the interactive cell usually
    works, but the object's own footprint can span two rows (a gate's V-row), so
    this walks outward through the object's own PASSABLE cells (never its blocking
    ones) to find the first genuine, non-footprint zone tile reachable -- fixes
    the s7-z4 defect (2026-09): the interior neighbor could be sealed shut by
    _seal_all_passages (which seals the zone's full raw perimeter, not just the
    entrance actually used) while a naive one-hop check missed it because it sat
    two cells away, past the gate's own V-row."""
    footprint = {(cx, cy) for cx, cy, _blk in footprint_cells}
    passable_footprint = {(cx, cy) for cx, cy, blk in footprint_cells if not blk}
    frontier = set(interactive)
    visited = set(frontier)
    for _ in range(len(footprint) + 1):
        nxt: set[Tile] = set()
        for fx, fy in frontier:
            for dx, dy in _DIRS8:
                nb = (fx + dx, fy + dy)
                if nb in visited:
                    continue
                if nb in ts and nb not in footprint:
                    return nb
                if nb in passable_footprint:
                    visited.add(nb)
                    nxt.add(nb)
        frontier = nxt
        if not frontier:
            break
    return None


def _entry_tile_has_stray_leak(
    entry_tile: Tile,
    footprint_cells: Sequence[tuple[int, int, bool]],
    ts: AbstractSet[Tile],
    all_ts: AbstractSet[Tile],
    blocked_ts: AbstractSet[Tile],
) -> bool:
    """True if the doorway tile just behind the gate/monolith is 8-adjacent to a tile
    outside `ts` that is NOT part of the access object's own footprint AND not
    already blocked (by that neighbouring zone's own pre-existing vegetation/objects)
    -- a leak unrelated to the gate/monolith itself, letting a hero step in or out
    sideways without ever touching its interactive tile (s7-z4 defect, 2026-09,
    fourth occurrence: the entry tile sits right behind the gate almost by
    definition, so it is expected to border the gate's own exterior side -- but it
    must not ALSO border genuinely open ground in a completely different
    neighbouring zone). `blocked_ts` is `_blocked_ts` -- object-blocking-aware, so an
    already-vegetated neighbouring border reads as sealed even though it is raw
    zone-tile-adjacent to `ts`."""
    footprint = {(cx, cy) for cx, cy, _blk in footprint_cells}
    ext_ts = all_ts - ts
    return any(
        (entry_tile[0] + dx, entry_tile[1] + dy) in ext_ts
        and (entry_tile[0] + dx, entry_tile[1] + dy) not in footprint
        and (entry_tile[0] + dx, entry_tile[1] + dy) not in blocked_ts
        for dx, dy in _DIRS8
    )


def _reach8(seed_tiles: AbstractSet[Tile], avail: AbstractSet[Tile]) -> set[Tile]:
    d = {t for t in seed_tiles if t in avail}
    q = collections.deque(d)
    while q:
        cx, cy = q.popleft()
        for dx, dy in _DIRS8:
            nb = (cx + dx, cy + dy)
            if nb in avail and nb not in d:
                d.add(nb)
                q.append(nb)
    return d


def _path_prev(
    reached: AbstractSet[Tile],
    target: Tile,
    ts: AbstractSet[Tile],
    footprint: AbstractSet[Tile],
) -> dict[Tile, Tile] | None:
    prev: dict[Tile, Tile] = {}
    seen = set(reached)
    q = collections.deque(reached)
    while q:
        cx, cy = q.popleft()
        if (cx, cy) == target:
            return prev
        for dx, dy in _DIRS8:
            nb = (cx + dx, cy + dy)
            if nb in ts and nb not in footprint and nb not in seen:
                seen.add(nb)
                prev[nb] = (cx, cy)
                q.append(nb)
    return None


def find_entry_corridor(
    entry_tile: Tile | None,
    footprint_cells: Sequence[tuple[int, int, bool]],
    ts: AbstractSet[Tile],
    all_ts: AbstractSet[Tile],
) -> set[Tile]:
    """The MINIMAL set of `ts` tiles beyond `entry_tile` that must stay unsealed to
    keep every INTERIOR tile (`ts` minus the true outer boundary) connected to the
    gate/monolith once `_seal_all_passages` closes off everything else. `entry_tile`
    alone only fixes a single-tile-deep doorway; a loot zone's own interior shape can
    put a further boundary-classified neck BEHIND that first tile (s7-z4 defect,
    2026-09, second occurrence: a 1-tile vestibule separated from the rest of the
    zone's room by a whole neck row that also qualifies as 'boundary' -- adjacent to
    tiles outside `ts` -- and so got fully sealed, leaving only the vestibule
    reachable from the gate).

    Grows the corridor ONE missing connection at a time (not a blanket union of every
    interior tile's own shortest-path ancestors -- s9-z3 defect, 2026-09, third
    occurrence: that over-eager version could pull an entire boundary-classified room
    edge into the corridor merely because it sat on some deep interior tile's
    arbitrary BFS-tie-broken shortest path, even though that interior tile was ALSO
    reachable another way -- permanently exempting a real external leak on that edge
    from sealing). Each iteration: find the nearest still-disconnected interior tile,
    connect it via the shortest path over the full `ts` graph, add ONLY the new tiles
    on that path, and recheck -- so a boundary tile is exempted from sealing only
    when NO other route reaches the interior without it.

    `all_ts` is the union of every zone's own tiles (this zone's own boundary is
    whatever of `ts` borders a tile OUTSIDE `ts` but still in `all_ts`)."""
    if entry_tile is None:
        return set()
    footprint = {(cx, cy) for cx, cy, _blk in footprint_cells}
    ext_ts = all_ts - ts
    boundary = {t for t in ts if any((t[0] + dx, t[1] + dy) in ext_ts for dx, dy in _DIRS8)}
    interior = ts - boundary

    corridor = {entry_tile}
    reached = _reach8({entry_tile}, interior | corridor)
    orphans = interior - reached
    while orphans:
        target = min(orphans)
        prev = _path_prev(reached, target, ts, footprint)
        if prev is None:
            break  # unreachable within ts at all -- shouldn't happen, ts is connected
        cur: Tile | None = target
        while cur not in reached:
            corridor.add(cur)
            cur = prev.get(cur)
            if cur is None:
                break
        reached = _reach8({entry_tile}, interior | corridor)
        orphans = interior - reached
    return corridor


def shrine_spell_level(anim: str) -> int:
    """Spell level a shrine teaches from its animation name (avxlNsh0 → N), or 0 if not a shrine."""
    m = re.match(r"avxl(\d)sh", anim, re.IGNORECASE)
    return int(m.group(1)) if m else 0


def solo_visit_pool(
    terrain: str,
    exclude_anims: Collection[str] = (),
    min_shrine_level: int | None = None,
) -> list[Identity]:
    """Objects with exactly one visit tile and no blocking body cells — the 'christmas-green'
    category (shrines, magic wells, fountains, etc.).  These fit inside a single open tile
    and are safe to cache inside pockets.

    exclude_anims: animation names to skip entirely.
    min_shrine_level: when set, shrines teaching spells below this level are excluded
        (non-shrine objects are unaffected)."""
    pool: list[Identity] = []
    seen: set[str] = set()
    for purpose in _SOLO_VIS_PURPOSES:
        for ident in ON.pool(purpose, terrain):
            anim = ident.animation.lower()
            if anim in seen or anim in exclude_anims:
                continue
            if min_shrine_level is not None:
                lvl = shrine_spell_level(anim)
                if lvl > 0 and lvl < min_shrine_level:
                    continue
            mask = ident.mask
            n_visit = sum(1 for row in mask for ch in row if ch in "AX")
            n_body = sum(1 for row in mask for ch in row if ch == "B")
            if n_visit == 1 and n_body == 0:
                seen.add(anim)
                pool.append(ident)
    return pool


def _blocking_cells(objs: Iterable[PlacedObject]) -> set[Tile]:
    blocked: set[Tile] = set()
    for o in objs:
        for cx, cy, blk in OR.mask_cells(o.mask, o.x, o.y):
            if blk:
                blocked.add((cx, cy))
    return blocked


def _count_clusters(boundary: AbstractSet[Tile]) -> int:
    seen: set[Tile] = set()
    n = 0
    for s in sorted(boundary):
        if s in seen:
            continue
        n += 1
        q = collections.deque([s])
        seen.add(s)
        while q:
            cx, cy = q.popleft()
            for dx, dy in _DIRS8:
                nb = (cx + dx, cy + dy)
                if nb in boundary and nb not in seen:
                    seen.add(nb)
                    q.append(nb)
    return n


def _passage_components(
    zr: ZoneRecord, all_ts: AbstractSet[Tile], blocked_ts: AbstractSet[Tile]
) -> tuple[int, frozenset[Tile]]:
    """Count 8-connected clusters of ACTUALLY PASSABLE zone tiles that border an
    actually-passable tile of another zone -- object-blocking aware (the same
    notion PassageOverlay's 'blue' renders), not just raw zone-terrain adjacency,
    which would merge separate real gaps whenever the vegetation step's border
    walls still leave the zone's raw perimeter one contiguous terrain-adjacency
    strip. This is the topological single-entrance check: 1 cluster = 1 direction
    of connectivity. Returns (n_clusters, frozenset_of_boundary_tiles)."""
    ts = zr.ts - blocked_ts
    ext_ts = (all_ts - zr.ts) - blocked_ts
    boundary = {t for t in ts if any((t[0] + dx, t[1] + dy) in ext_ts for dx, dy in _DIRS8)}
    return _count_clusters(boundary), frozenset(boundary)


def _anchor_clear(cand: ZoneRecord, t: Tile) -> bool:
    ts_set = cand.ts
    op_set = cand.open_set
    tx, ty = t
    # [N N]   (tx-1,ty-1) (tx,  ty-1)
    # [N X]   (tx-1,ty)   (tx,  ty)  ← anchor
    # All three N-cells must be clear: either outside this zone or
    # inside it and in open_set (not occupied by vegetation or objects).
    return all(
        (cx, cy) not in ts_set or ((cx, cy) in op_set and (cx, cy) not in cand.used)
        for cx, cy in ((tx - 1, ty - 1), (tx, ty - 1), (tx - 1, ty))
    )


def _try_guard_ring(ext_zr: ZoneRecord, ext_t: Tile, target: PlaceTarget, spec: PlaceSpec) -> bool:
    for t in sorted(
        ext_zr.reach - ext_zr.used,
        key=lambda t: max(abs(t[0] - ext_t[0]), abs(t[1] - ext_t[1])),
    ):
        if max(abs(t[0] - ext_t[0]), abs(t[1] - ext_t[1])) > 1:
            break
        if place_one(target, spec, t[0], t[1]):
            return True
    return False


@dataclass(frozen=True, slots=True)
class _GateAim:
    passage_side: str
    bbox_x0: int
    bbox_x1: int
    bbox_y0: int
    bbox_y1: int
    passage_cx: float
    passage_cy: float

    @classmethod
    def of(cls, ts: AbstractSet[Tile], passage_cx: float, passage_cy: float) -> Self:
        # Determine which side of the loot zone's bounding box the passage is on.
        ts_xs = [t[0] for t in ts]
        ts_ys = [t[1] for t in ts]
        bbox_x0, bbox_x1 = min(ts_xs), max(ts_xs)
        bbox_y0, bbox_y1 = min(ts_ys), max(ts_ys)
        d_top = passage_cy - bbox_y0
        d_bottom = bbox_y1 - passage_cy
        d_left = passage_cx - bbox_x0
        d_right = bbox_x1 - passage_cx
        side_dists: list[tuple[str, float]] = [
            ("top", d_top),
            ("bottom", d_bottom),
            ("left", d_left),
            ("right", d_right),
        ]
        passage_side = min(side_dists, key=itemgetter(1))[0]
        return cls(passage_side, bbox_x0, bbox_x1, bbox_y0, bbox_y1, passage_cx, passage_cy)

    def score(self, t: Tile) -> tuple[float, float]:
        gx, gy = t
        if self.passage_side in ("top", "bottom"):
            bnd_y = self.bbox_y0 if self.passage_side == "top" else self.bbox_y1
            return (abs(gy - bnd_y), abs((gx - 1.5) - self.passage_cx))
        else:  # left / right
            # anchor x so gate's span (gx-3 .. gx) covers the passage x
            ideal_x = self.bbox_x0 + 3 if self.passage_side == "left" else self.bbox_x1
            return (abs(gy - self.passage_cy), abs(gx - ideal_x))


@dataclass(frozen=True, slots=True)
class _LootZone:
    zid: int
    terrain: str
    st: PG.TerrainStats
    ts: frozenset[Tile]
    used: set[Tile]
    rng: random.Random
    ext_pools: tuple[Sequence[ZoneRecord], ...]
    open_set: frozenset[Tile]
    reach: frozenset[Tile]


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
        # Hero-strengthening structures: an explicit allow-list (user-mandated), not
        # "every solo-visitable object" -- see _LOOT_HERO_STRUCTURE_TYPES.
        pool_vis = [
            i for i in ON.pool("STAT_PERMANENT", terrain) if i.type in _LOOT_HERO_STRUCTURE_TYPES
        ]
        pool_art = [
            i for i in ON.pool("REWARD_PICKUP", terrain) if i.type not in _LOOT_ART_EXCL_TYPES
        ]
        pool_res = ON.pool("RESOURCE_PILE", terrain)
        # chest-type: treasure chests, campfires, pandora's box, scholar (loot-zone only),
        # plus a fixed level 4-5 spell scroll (its own kind below, not from ON.gameplay_pool
        # -- a spell scroll's `subtype` IS the spell identifier, an ontology-classified
        # value, not a plain terrain pool entry). Grouped by KIND so the roll below picks
        # one of the five kinds uniformly, then an identity within it -- otherwise the 25
        # individual level-4/5 spells would swamp the single treasureChest/campfire/
        # pandoraBox/scholar entries in a flat random choice.
        pool_chest = [
            i for i in pool_art if i.type in LOOT_CHEST_TYPES + _LOOT_ZONE_CHEST_EXTRA_TYPES
        ]
        chest_kind_pools: dict[str, list[Identity]] = {
            kind: [i for i in pool_chest if i.type == kind]
            for kind in LOOT_CHEST_TYPES + _LOOT_ZONE_CHEST_EXTRA_TYPES
        }
        chest_kind_pools["spellScroll"] = [
            Identity(type="spellScroll", subtype=n, animation="ava0001", mask=("A",))
            for lvl in _LOOT_SCROLL_LEVELS
            for n in ON.spells_by_level(lvl)
        ]
        # High-tier artifacts only (major + relic, i.e. level >= 3).
        arts_high = [(a, _LOOT_ART_W[a]) for a in ("avarnd3", "avarnd4") if a in _LOOT_ART_W]
        # Rare resources: mercury, sulfur, crystal, gems, gold — no wood/ore/randomResource.
        pool_rare = [i for i in pool_res if i.subtype in _LOOT_RARE_RESOURCE_SUBTYPES]
        return cls(pool_vis, pool_art, pool_res, chest_kind_pools, arts_high, pool_rare)


@final
class _LootZonePlacer:
    def __init__(
        self,
        zone_records: list[ZoneRecord],
        objs_existing: list[PlacedObject],
        seed: int,
        bounds: tuple[int, int] | None,
        fixed: Sequence[PlacedObject],
    ) -> None:
        self.zone_records = zone_records
        self.objs_existing = objs_existing
        self.seed = seed
        self.bounds = bounds
        self.fixed = fixed
        self.town_tiles = {(o.x, o.y) for o in objs_existing if o.purpose == "TOWN"}
        self.cover = CoverIndex([*fixed, *objs_existing])

        # Pre-compute full tile set of all zones for boundary detection.
        self.all_ts: set[Tile] = set()
        for zr in zone_records:
            self.all_ts |= zr.ts

        # Tiles blocked by an already-placed object (gameplay + the vegetation step's
        # border-densifying walls, both already committed to objs_existing by the time
        # this runs) -- needed so the single-entrance check below measures ACTUAL
        # passable connectivity, not raw zone-terrain adjacency. Mirrors
        # renderers.overlays._tiles.passable_tiles's blocking half (no terrain grid
        # needed here: zone/ext tile sets are already land-only).
        self.blocked_ts = _blocking_cells(o for o in objs_existing if o.level == 0)

        self.ext_no_castle: list[ZoneRecord] = []
        self.ext_any: list[ZoneRecord] = []
        self.placed_ext_tiles: list[Tile] = []  # positions of exterior partners already placed
        self.objs: list[PlacedObject] = []
        self.n_placed = 0
        self.processed_loot_zids: set[int] = (
            set()
        )  # zones whose entrance was actually sealed this run
        self.gate_count, self.mono_count = 0, 0

    def run(self) -> tuple[list[PlacedObject], int, set[int]]:
        loot_zrs = self._loot_zones()
        if not loot_zrs:
            return [], 0, set()

        loot_zids = {zr.zid for zr, _ in loot_zrs}
        self.ext_no_castle = [
            zr
            for zr in self.zone_records
            if zr.zid not in loot_zids and not any(t in self.town_tiles for t in zr.ts)
        ]
        self.ext_any = [zr for zr in self.zone_records if zr.zid not in loot_zids]

        for loot_zr, passage_tiles in sorted(loot_zrs, key=lambda x: x[0].zid):
            self._process(loot_zr, passage_tiles)
        return self.objs, self.n_placed, self.processed_loot_zids

    def _loot_zones(self) -> list[tuple[ZoneRecord, frozenset[Tile]]]:
        loot_zrs: list[tuple[ZoneRecord, frozenset[Tile]]] = []  # (zone_record, passage_tiles)
        for zr in self.zone_records:
            if len(zr.ts) > LOOT_ZONE_MAX_TILES:
                continue
            if any(t in self.town_tiles for t in zr.ts):
                continue
            n_clusters, passage_tiles = _passage_components(zr, self.all_ts, self.blocked_ts)
            if n_clusters != 1:
                continue
            loot_zrs.append((zr, passage_tiles))
        return loot_zrs

    def _remoteness(self, x: float, y: float) -> float:
        d_castle = (
            min((x - tx) ** 2 + (y - ty) ** 2 for tx, ty in self.town_tiles) ** 0.5
            if self.town_tiles
            else 1e9
        )
        d_partner = (
            min((x - px) ** 2 + (y - py) ** 2 for px, py in self.placed_ext_tiles) ** 0.5
            if self.placed_ext_tiles
            else 1e9
        )
        return d_castle + d_partner

    def _far_score(self, zr: ZoneRecord) -> tuple[float, ...]:
        free = zr.reach - zr.used
        if not free:
            return (-1, 0, 0)
        cx = sum(x for x, _ in zr.ts) / len(zr.ts)
        cy = sum(y for _, y in zr.ts) / len(zr.ts)
        return (self._remoteness(cx, cy), len(free))

    def _find_ext_spot(
        self, ext_ident: Identity, ext_pools: Iterable[Sequence[ZoneRecord]]
    ) -> tuple[ZoneRecord, Tile] | None:
        """Return (zone_record, tile) farthest from castles and from existing
        exterior partners (keymasters / exterior monoliths already placed)."""
        for pool in ext_pools:
            spot = self._find_ext_spot_in(ext_ident, pool)
            if spot is not None:
                return spot
        return None

    def _find_ext_spot_in(
        self, ext_ident: Identity, ext_pool: Sequence[ZoneRecord]
    ) -> tuple[ZoneRecord, Tile] | None:
        for cand in sorted(ext_pool, key=self._far_score, reverse=True):
            free = sorted(cand.reach - cand.used)
            if not free:
                continue
            free.sort(key=lambda t: self._remoteness(t[0], t[1]), reverse=True)
            for t in free:
                if not _anchor_clear(cand, t):
                    continue
                tx, ty = t
                if (
                    legal_cells(
                        ext_ident, (tx, ty), cand.reach, cand.used, CellRules(bounds=self.bounds)
                    )
                    is not None
                ):
                    return cand, t
        return None

    def _target(self, zone: _LootZone) -> PlaceTarget:
        return PlaceTarget(
            self.objs,
            zone.used,
            zone.reach,
            zone.rng,
            zone.st,
            bounds=self.bounds,
            cover=self.cover,
        )

    def _seal_all_passages(self, zone: _LootZone, skip_cells: Collection[Tile] = ()) -> None:
        """Fill EVERY boundary tile of the loot zone (tile in ts that is 8-adjacent
        to a tile outside ts) with a single-cell blocking vegetation object, perfectly
        sealing the perimeter including any passable V-overlay cells of the gate.

        skip_cells: the gate's or monolith's full footprint, its interactive tile(s) and
        entry corridor; these are NOT sealed. Without the footprint a boundary-adjacent
        non-interactive footprint cell (e.g. one of a monolith's 3 non-interactive 'V'
        cells) got a second, conflicting decor object stacked directly onto it (s9-z3
        defect, 2026-09). Loot fill may still put a pickup there, and
        `_close_stray_leaks` seals the outside tile if that leaves a leak."""
        ts = zone.ts
        used = zone.used
        ext_ts = self.all_ts - ts
        veg_pool = ON.decor_pool(
            zone.terrain, blocking=True, max_cells=1, exclude_types=_LOOT_EXCL_DECOR
        )
        if not veg_pool:
            return
        for t in sorted(ts):
            if t in skip_cells or t in used:
                continue  # access object's interactive tile, or its own footprint
            tx, ty = t
            if not any((tx + dx, ty + dy) in ext_ts for dx, dy in _DIRS8):
                continue  # interior tile — left for loot
            kept = [o for o in self.objs if not (o.purpose == "GUARD" and o.x == tx and o.y == ty)]
            if len(kept) != len(self.objs):
                self.objs[:] = kept
                self.cover.reset([*self.fixed, *self.objs_existing, *self.objs])
            iv = zone.rng.choice(veg_pool)
            decor = PlacedObject.at(iv, (tx, ty), purpose="")
            if self.cover.try_add(decor):
                used.add(t)
                self.objs.append(decor)

    def _close_stray_leaks(
        self,
        ts: AbstractSet[Tile],
        access_interactive: AbstractSet[Tile],
        rng: random.Random,
    ) -> None:
        """Final correctness pass, run once the gate/monolith, its corridor and its
        fill are all committed: verify NO 8-connected path exists from any `ts` tile
        to any tile outside `ts` except through `access_interactive`, and close every
        leak found by sealing the OUTSIDE tile (in whichever neighbouring zone it
        belongs to). `_seal_all_passages` only ever places blockers inside `ts` -- it
        cannot, by itself, close a leak whose open side sits in a DIFFERENT zone
        (s7-z4 defect, 2026-09, fifth occurrence: placing the gate clears any
        existing object whose footprint grazes the gate's own -- including a
        neighbouring zone's vegetation object anchored just outside `ts` whose
        DECORATIVE overlay cell happened to graze the gate's own V-row, even though
        that same object's actual BLOCKING cell, which had been sealing this exact
        leak, sat outside the gate's footprint entirely and was needlessly swept away
        with it). Mutates the neighbouring zone's own `used` set too, so later steps
        never place something conflicting there."""
        zone_of: dict[Tile, ZoneRecord] = {}
        for zr in self.zone_records:
            for t in zr.ts:
                zone_of[t] = zr
        ext_ts = self.all_ts - ts
        blocked = _blocking_cells(self.objs_existing + self.objs)
        veg_cache: dict[str, list[Identity]] = {}
        for t in sorted(ts):
            if t in access_interactive or t in blocked:
                continue
            for dx, dy in _DIRS8:
                nb = (t[0] + dx, t[1] + dy)
                if nb not in ext_ts or nb in blocked:
                    continue
                nb_zr = zone_of.get(nb)
                if nb_zr is None or nb in nb_zr.used:
                    continue
                self._seal_outside(nb, nb_zr, veg_cache, rng, blocked)

    def _seal_outside(
        self,
        nb: Tile,
        nb_zr: ZoneRecord,
        veg_cache: dict[str, list[Identity]],
        rng: random.Random,
        blocked: set[Tile],
    ) -> None:
        nb_terrain = nb_zr.terrain
        if nb_terrain not in veg_cache:
            veg_cache[nb_terrain] = ON.decor_pool(
                nb_terrain, blocking=True, max_cells=1, exclude_types=_LOOT_EXCL_DECOR
            )
        pool = veg_cache[nb_terrain]
        if not pool:
            return
        iv = rng.choice(pool)
        decor = PlacedObject.at(iv, nb, purpose="")
        if not self.cover.try_add(decor):
            return
        self.objs.append(decor)
        nb_zr.used.add(nb)
        blocked.add(nb)

    def _fill_loot(self, zone: _LootZone, access_footprint: AbstractSet[Tile]) -> None:
        """Loot fill: background decor → hero-strengthening structures → mixed rewards.

        Pass 0 (bg): non-blocking terrain decor on interior tiles (under gameplay objects).
        Pass 1: TWO of each whitelisted hero-strengthening structure, separated from
                each other (never adjacent), tile availability permitting (user-mandated
                2026-09).
        Pass 2: a roll per still-free tile -- 20 % major/relic artifact, 40 % chest
                (treasure chest / campfire / pandora's box / scholar / a fixed level 4-5
                spell scroll), 40 % rare resource pile (mercury, sulfur, crystal, gems,
                gold — no wood/ore) -- and EVERY tile Pass 1 left free must end up
                occupied by something (falling back through a plain resource pile if its
                rolled pick doesn't fit): a sealed loot zone with even one unclaimed
                interior tile is a tile a boat could dock a hero onto directly, walking
                straight in without ever touching the gate/monolith (user-mandated)."""
        self._fill_background(zone)
        pools = _LootPools.of(zone.terrain)

        free = sorted(zone.reach - zone.used)
        zone.rng.shuffle(free)

        target = self._target(zone)
        self._fill_hero_structures(zone, target, pools.pool_vis, free)
        self._fill_rolls(zone, target, pools)
        self._fill_remaining(zone, target, pools, access_footprint)

    def _fill_background(self, zone: _LootZone) -> None:
        # Pass 0: background — non-blocking terrain decor on interior (non-boundary) tiles.
        reach = zone.reach
        ext_ts_inner = self.all_ts - reach
        interior = {
            t for t in reach if not any((t[0] + dx, t[1] + dy) in ext_ts_inner for dx, dy in _DIRS8)
        }
        pool_bg = ON.decor_pool(
            zone.terrain, blocking=False, max_cells=1, exclude_types=_LOOT_EXCL_DECOR
        )
        if pool_bg:
            for t in sorted(interior):
                if zone.rng.random() < 0.5:
                    iv = zone.rng.choice(pool_bg)
                    decor = PlacedObject.at(iv, t, purpose="")
                    if self.cover.try_add(decor):
                        self.objs.append(decor)

    @staticmethod
    def _fill_hero_structures(
        zone: _LootZone, target: PlaceTarget, pool_vis: Sequence[Identity], free: Sequence[Tile]
    ) -> None:
        # Pass 1: TWO of each whitelisted hero-strengthening structure, separated from
        # each other by >= LOOT_HERO_STRUCTURE_MIN_SEP (never adjacent/touching), tile
        # availability permitting (user-mandated 2026-09).
        for struct_type in sorted(_LOOT_HERO_STRUCTURE_TYPES):
            candidates = [i for i in pool_vis if i.type == struct_type]
            if not candidates:
                continue
            iv = zone.rng.choice(candidates)
            spec = PlaceSpec("BONUS_TEMP", None, ident=iv, cache=True, interactive_only=True)
            placed_at: list[Tile] = []
            for t in free:
                if len(placed_at) >= _LOOT_HERO_STRUCTURE_COUNT:
                    break
                if t in zone.used:
                    continue
                if any(
                    max(abs(t[0] - p[0]), abs(t[1] - p[1])) < LOOT_HERO_STRUCTURE_MIN_SEP
                    for p in placed_at
                ):
                    continue
                if place_one(target, spec, t[0], t[1]):
                    placed_at.append(t)

    @staticmethod
    def _fill_rolls(zone: _LootZone, target: PlaceTarget, pools: _LootPools) -> None:
        # Pass 2: a roll per tile -- 20 % major/relic artifact | 40 % chest (treasure
        # chest / campfire / pandora's box / scholar / a fixed level 4-5 spell scroll --
        # never corpse or any other REWARD_PICKUP type) | 40 % rare resource. A rolled
        # pick that doesn't fit just leaves the tile for Pass 3, no in-pass fallback.
        rng = zone.rng
        arts_high = pools.arts_high
        chest_kinds = [k for k, p in pools.chest_kind_pools.items() if p]
        for t in sorted(zone.reach - zone.used):
            roll = rng.random()
            if roll < 0.2 and arts_high:
                ai = ON.identity_of(
                    rng.choices([a for a, _ in arts_high], weights=[w for _, w in arts_high], k=1)[
                        0
                    ]
                )
                _ = place_one(
                    target,
                    PlaceSpec(
                        "REWARD_PICKUP", pools.pool_art, ident=ai, cache=True, interactive_only=True
                    ),
                    t[0],
                    t[1],
                )
            elif roll < 0.6 and chest_kinds:
                ident = rng.choice(pools.chest_kind_pools[rng.choice(chest_kinds)])
                _ = place_one(
                    target,
                    PlaceSpec(
                        "REWARD_PICKUP",
                        pools.pool_art,
                        ident=ident,
                        cache=True,
                        interactive_only=True,
                    ),
                    t[0],
                    t[1],
                )
            elif pools.pool_rare:
                _ = place_one(
                    target,
                    PlaceSpec(
                        "RESOURCE_PILE",
                        pools.pool_res,
                        ident=rng.choice(pools.pool_rare),
                        cache=True,
                        interactive_only=True,
                    ),
                    t[0],
                    t[1],
                )

    def _fill_remaining(
        self,
        zone: _LootZone,
        target: PlaceTarget,
        pools: _LootPools,
        access_footprint: AbstractSet[Tile],
    ) -> None:
        # Pass 3: any tile Pass 2 left free gets a rare resource -- a sealed loot zone
        # can't leave ANY tile unclaimed (a boat could dock a hero directly onto it,
        # bypassing the gate/monolith entirely, user-mandated). Falls back to any
        # resource, then warns, only in the pathological case where even that fails.
        pool_rare = pools.pool_rare
        pool_res = pools.pool_res
        for t in sorted(zone.reach - zone.used):
            placed = bool(pool_rare) and place_one(
                target,
                PlaceSpec(
                    "RESOURCE_PILE",
                    pool_res,
                    ident=zone.rng.choice(pool_rare),
                    cache=True,
                    interactive_only=True,
                ),
                t[0],
                t[1],
            )
            if not placed and pool_res:
                placed = place_one(
                    target,
                    PlaceSpec("RESOURCE_PILE", pool_res, cache=True, interactive_only=True),
                    t[0],
                    t[1],
                )
            if not placed and t not in access_footprint:
                placed = self._fill_decor(zone, t)
            if not placed:
                print(
                    f"  WARNING: loot zone fill left tile {t} unclaimed "
                    + f"(no fitting identity for terrain {zone.terrain!r})"
                )

    def _fill_decor(self, zone: _LootZone, t: Tile) -> bool:
        fillers = ON.decor_pool(
            zone.terrain, blocking=True, max_cells=1, exclude_types=_LOOT_EXCL_DECOR
        )
        if fillers:
            decor = PlacedObject.at(zone.rng.choice(fillers), t, purpose="")
            if self.cover.try_add(decor):
                zone.used.add(t)
                self.objs.append(decor)
                return True
        return False

    def _process(self, loot_zr: ZoneRecord, passage_tiles: frozenset[Tile]) -> None:
        zid = loot_zr.zid
        terrain = loot_zr.terrain
        st = PG.mine_gameplay()[terrain]
        ts = loot_zr.ts
        used = loot_zr.used
        rng = random.Random(self.seed ^ (zid * 92821) ^ 0xA117)
        ext_pools = (self.ext_no_castle, self.ext_any)
        passage_cx = sum(t[0] for t in passage_tiles) / len(passage_tiles)
        passage_cy = sum(t[1] for t in passage_tiles) / len(passage_tiles)
        snapshot = _PlacerSnapshot.of(self)

        # Clear scatter vegetation so the whole interior is available for loot.
        self.objs_existing[:] = [o for o in self.objs_existing if (o.x, o.y) not in ts]
        self.objs[:] = [o for o in self.objs if (o.x, o.y) not in ts]
        self.cover.reset([*self.fixed, *self.objs_existing, *self.objs])
        used.clear()
        # After clearing, all zone tiles are passable (loot zones have no gameplay
        # blockers — no town, no mine).  The stored open_set/reach were computed with
        # dense vegetation in place (~70 % blocking) so they cover only ~30 % of ts.
        # Reset both to the full tile set so seal and fill can reach every tile.
        zone = _LootZone(zid, terrain, st, ts, used, rng, ext_pools, open_set=ts, reach=ts)

        aim = _GateAim.of(ts, passage_cx, passage_cy)

        use_gate = rng.random() < 0.5
        placed = self._place_gate(zone, aim) if use_gate else self._place_monolith(zone)
        if not placed:
            snapshot.restore(self)

    def _place_gate(self, zone: _LootZone, aim: _GateAim) -> bool:
        # ── Border Gate + Keymaster ──────────────────────────────────────
        # Gate mask ['VVVV','VBXB']: 4-wide x 2-tall, anchor = bottom-right.
        # V-row at y-1 (passable/exterior), blocking-row at y (loot zone side).
        # Sort candidates so the blocking-row aligns with the passage side:
        #   top/bottom → anchor y at boundary row, x centred on passage
        #   left/right → anchor y at passage cy, x so the gate span covers passage x
        gate_anim, key_anim = _LOOT_COLORS[self.gate_count % len(_LOOT_COLORS)]
        gate_ident = ON.identity_of(gate_anim)
        key_ident = ON.identity_of(key_anim)

        km_spot = self._find_ext_spot(key_ident, zone.ext_pools)
        if km_spot is None:
            return False

        sited = self._site_gate(zone, aim, gate_ident)
        if sited is None:
            return False
        gate_tile, entry_tile, _gate_cells, interactive = sited

        # Check exterior access: at least one non-loot-zone tile adjacent to
        # the interactive cell must be passable (not occupied/blocked by objects).
        if not self._has_ext_access(zone.ts, interactive):
            return False

        # Excavate the full doorway corridor BEFORE the free-tile scan below: never
        # vegetation-sealed -- otherwise the gate is a wall with no interior side,
        # or (s7-z4 second occurrence, 2026-09) opens onto a 1-tile vestibule sealed
        # off from the rest of the zone's own room by a further boundary-classified
        # neck _find_entry_tile alone didn't reach. Once excavated the corridor is
        # ordinary walkable floor like any other interior tile -- NOT reserved as an
        # empty hallway (s7-z4 third occurrence, 2026-09: corridor tiles used to get
        # `used.add`-ed right here, before `_fill_loot`'s own free-tile scan ever
        # saw them, so 3-5 genuinely reachable tiles right behind the gate stayed
        # unfilled forever). Loot fill uses `interactive_only` placement (a walk-on
        # 'A' cell), so a resource pile or structure sitting in the corridor never
        # blocks the hero's path through it.
        self._seal_and_fill(
            zone,
            entry_tile,
            list(OR.mask_cells(gate_ident.mask, gate_tile[0], gate_tile[1])),
            set(interactive),
        )

        if not self._place_ext_partner(zone.zid, km_spot, key_ident, "QUEST_GATE"):
            return False
        self.gate_count += 1
        return True

    def _site_gate(
        self, zone: _LootZone, aim: _GateAim, gate_ident: Identity
    ) -> tuple[Tile, Tile, list[Tile], list[Tile]] | None:
        ts = zone.ts
        for t in sorted(ts, key=aim.score):
            gx, gy = t
            gate_cells = [(cx, cy) for cx, cy, _ in OR.mask_cells(gate_ident.mask, gx, gy)]
            if self.bounds:
                bw, bh = self.bounds
                if any(not (0 <= cx < bw and 0 <= cy < bh) for cx, cy in gate_cells):
                    continue
            interactive = OR.mask_interactive_cells(gate_ident.mask, gx, gy)
            if not all(c in zone.open_set for c in interactive):
                continue
            # The tile(s) directly behind the interactive cell, on the loot-zone
            # side, must include at least one usable doorway -- the interior tile
            # the hero actually steps onto once the gate opens. Without one, the
            # gate opens onto a wall (s7-z4 diagnosis, 2026-09): the zone's raw
            # perimeter can extend past the passage the eligibility check found
            # (e.g. a narrow zone whose sides are also boundary), and
            # _seal_all_passages seals ALL of that perimeter, not just the
            # detected passage cluster.
            entry_tile_cand = _find_entry_tile(
                interactive, list(OR.mask_cells(gate_ident.mask, gx, gy)), ts
            )
            if entry_tile_cand is None:
                continue
            if _entry_tile_has_stray_leak(
                entry_tile_cand,
                list(OR.mask_cells(gate_ident.mask, gx, gy)),
                ts,
                self.all_ts,
                self.blocked_ts,
            ):
                continue
            if self._commit_gate(zone, gate_ident, t, gate_cells):
                return t, entry_tile_cand, gate_cells, interactive
        return None

    def _commit_gate(
        self, zone: _LootZone, gate_ident: Identity, t: Tile, gate_cells: list[Tile]
    ) -> bool:
        gx, gy = t
        # Clear any object (vegetation, guard) whose footprint overlaps the gate's
        # full cell set — including V-row cells that may be in the exterior zone.
        fp = set(gate_cells)
        cleared: set[Tile] = set()
        for src in (self.objs_existing, self.objs):
            victims = [
                o
                for o in src
                if any((cx, cy) in fp for cx, cy, _ in OR.mask_cells(o.mask, o.x, o.y))
            ]
            for o in victims:
                src.remove(o)
                for cx, cy, _ in OR.mask_cells(o.mask, o.x, o.y):
                    cleared.add((cx, cy))
        self.cover.reset([*self.fixed, *self.objs_existing, *self.objs])
        for zr in self.zone_records:
            zr.used -= cleared
        zone.used.update(gate_cells)
        gate_obj = PlacedObject.at(gate_ident, (gx, gy), purpose="QUEST_GATE")
        # Allow approach from all 8 directions so the gate is
        # visitable from the exterior (above the VVVV row), not
        # only from the interior side.
        gate_obj.visitable_from = ("+++", "+-+", "+++")
        if not self.cover.try_add(gate_obj):
            zone.used.difference_update(gate_cells)
            return False
        self.objs.append(gate_obj)
        return True

    def _has_ext_access(self, ts: AbstractSet[Tile], interactive: Sequence[Tile]) -> bool:
        bounds = self.bounds
        ext_blocked = _blocking_cells(self.objs + self.objs_existing)
        return any(
            (sk[0] + dx, sk[1] + dy) not in ts
            and (sk[0] + dx, sk[1] + dy) not in ext_blocked
            and 0 <= sk[0] + dx < (bounds[0] if bounds else 999)
            and 0 <= sk[1] + dy < (bounds[1] if bounds else 999)
            for sk in interactive
            for dx, dy in _DIRS8
        )

    def _place_monolith(self, zone: _LootZone) -> bool:
        # ── Fully sealed + Two-Way Monolith pair ─────────────────────────
        mono_anim = _LOOT_MONOLITHS[self.mono_count % len(_LOOT_MONOLITHS)]
        mono_ident = ON.identity_of(mono_anim)

        ext_spot = self._find_ext_spot(mono_ident, zone.ext_pools)
        if ext_spot is None:
            return False

        sited = self._site_monolith(zone, mono_ident)
        if sited is None:
            return False
        int_t, entry_tile, mono_cells = sited

        if not place_one(
            self._target(zone),
            PlaceSpec("TRANSPORT", None, ident=mono_ident, interactive_only=True),
            int_t[0],
            int_t[1],
        ):
            return False
        mono_interactive = set(OR.mask_interactive_cells(mono_ident.mask, int_t[0], int_t[1]))
        # Excavate BEFORE the free-tile scan; the corridor is then ordinary floor,
        # not a reserved empty hallway -- see the gate branch's identical comment.
        self._seal_and_fill(zone, entry_tile, mono_cells, mono_interactive)

        if not self._place_ext_partner(zone.zid, ext_spot, mono_ident, "TRANSPORT"):
            return False
        self.mono_count += 1
        return True

    def _site_monolith(
        self, zone: _LootZone, mono_ident: Identity
    ) -> tuple[Tile, Tile, list[tuple[int, int, bool]]] | None:
        # Place monolith at zone centroid (deepest interior tile). Its own
        # footprint is fully passable ('V'/'A', no blocking cells), but the hero
        # still needs a doorway beyond it to reach the zone's loot -- otherwise
        # they arrive and are stuck on the monolith with nothing reachable (the
        # same defect as an unlinked gate, see s7-z4 diagnosis, 2026-09).
        ts = zone.ts
        reach = zone.reach
        used = zone.used
        ts_cx = sum(t[0] for t in ts) / len(ts)
        ts_cy = sum(t[1] for t in ts) / len(ts)
        for t in sorted(
            reach - used, key=lambda c, cx=ts_cx, cy=ts_cy: (c[0] - cx) ** 2 + (c[1] - cy) ** 2
        ):
            if legal_cells(mono_ident, t, reach, used, CellRules(bounds=self.bounds)) is None:
                continue
            mono_cells = list(OR.mask_cells(mono_ident.mask, t[0], t[1]))
            mono_fp_coords = {(cx, cy) for cx, cy, _blk in mono_cells}
            entry_tile_cand = _find_entry_tile(mono_fp_coords, mono_cells, ts)
            if entry_tile_cand is None:
                continue
            if _entry_tile_has_stray_leak(
                entry_tile_cand, mono_cells, ts, self.all_ts, self.blocked_ts
            ):
                continue
            return t, entry_tile_cand, mono_cells
        return None

    def _seal_and_fill(
        self,
        zone: _LootZone,
        entry_tile: Tile,
        footprint_cells: Sequence[tuple[int, int, bool]],
        access_interactive: set[Tile],
    ) -> None:
        footprint = {(cx, cy) for cx, cy, _b in footprint_cells}
        corridor = find_entry_corridor(entry_tile, footprint_cells, zone.ts, self.all_ts)
        self._seal_all_passages(zone, skip_cells=access_interactive | footprint | corridor)
        self.processed_loot_zids.add(zone.zid)
        self._fill_loot(zone, footprint)
        self._close_stray_leaks(zone.ts, access_interactive, zone.rng)

    def _place_ext_partner(
        self, zid: int, spot: tuple[ZoneRecord, Tile], ident: Identity, purpose: str
    ) -> bool:
        ext_zr, ext_t = spot
        ext_rng = random.Random(self.seed ^ (zid * 131071) ^ 0xCEBF)
        ext_st = PG.mine_gameplay()[ext_zr.terrain]
        target = PlaceTarget(
            self.objs,
            ext_zr.used,
            ext_zr.reach,
            ext_rng,
            ext_st,
            bounds=self.bounds,
            cover=self.cover,
        )
        spec = PlaceSpec(purpose, None, ident=ident)
        placed = place_one(target, spec, ext_t[0], ext_t[1])
        if not placed:
            for t in sorted(ext_zr.reach - ext_zr.used):
                if place_one(target, spec, t[0], t[1]):
                    placed = True
                    break
        if not placed:
            return False
        self.n_placed += 1
        self.placed_ext_tiles.append(ext_t)
        gident_ext = rnd_monster(7)
        decor_blk = OR.decor_blocking_cells(self.objs)
        for clear_of in (decor_blk, None):
            guard_spec = PlaceSpec("GUARD", None, ident=gident_ext, clear_of=clear_of)
            if _try_guard_ring(ext_zr, ext_t, target, guard_spec):
                break
        return True


@dataclass(frozen=True, slots=True)
class _PlacerSnapshot:
    objs_existing: list[PlacedObject]
    objs: list[PlacedObject]
    used: list[set[Tile]]
    processed_loot_zids: set[int]

    @classmethod
    def of(cls, placer: _LootZonePlacer) -> Self:
        return cls(
            list(placer.objs_existing),
            list(placer.objs),
            [set(zr.used) for zr in placer.zone_records],
            set(placer.processed_loot_zids),
        )

    def restore(self, placer: _LootZonePlacer) -> None:
        placer.objs_existing[:] = self.objs_existing
        placer.objs[:] = self.objs
        for zr, used in zip(placer.zone_records, self.used, strict=True):
            zr.used.clear()
            zr.used.update(used)
        placer.processed_loot_zids.clear()
        placer.processed_loot_zids.update(self.processed_loot_zids)
        placer.cover.reset([*placer.fixed, *placer.objs_existing, *placer.objs])


def place_loot_zones(
    zone_records: list[ZoneRecord],
    objs_existing: list[PlacedObject],
    seed: int = 1,
    bounds: tuple[int, int] | None = None,
    fixed: Sequence[PlacedObject] = (),
) -> tuple[list[PlacedObject], int, set[int]]:
    """Loot-zone access mechanic for small single-entrance zones.

    A 'loot zone' has ≤ LOOT_ZONE_MAX_TILES tiles, exactly one 8-connected cluster of
    'blue' passage tiles at its boundary (physical single-entrance check), and no town.
    Dense fill (hero-strengthening structures, major/relic artifacts, resource piles) is
    placed in EVERY tile of every qualifying zone -- including one bordering open water,
    since every non-access tile ends up occupied (see `_fill_loot`), leaving nothing a
    boat could dock a hero onto. Access mechanic is chosen 50/50 per zone:

      gate   (50 %): BORDER_GATE placed at the entrance + matching-colour KEYMASTER in a
               non-loot zone far from castles and far from other exterior partners.  The
               hero must first find the tent then return to the gate.  All other passage
               tiles are sealed with vegetation.

      mono   (50 %): all passage tiles are FULLY sealed — the zone becomes a walled
               pocket.  A TWO-WAY MONOLITH is placed inside and a matching one outside
               (far from castles and other exterior partners), so the only way in is the
               external monolith.

    The outer object (keymaster / exterior monolith) is pre-checked before the inner
    object is committed, so no permanently impassable gate or unreachable interior is
    ever left on the map.  Returns (objs, n_placements, sealed_zid_set).
    """
    return _LootZonePlacer(zone_records, objs_existing, seed, bounds, fixed).run()

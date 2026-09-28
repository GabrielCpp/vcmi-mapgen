"""Gated loot zones: a small zone with one passage gets sealed, and its only way in becomes a
Border Gate with its Keymaster outside, or a monolith pair."""

from __future__ import annotations

import collections
import math
import random
from collections.abc import Collection, Iterable, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from operator import itemgetter
from typing import Self, final

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.reach import reach
from vcmi_mapgen.core.model import CoverIndex, Identity, PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.placement.cells import CellRules, legal_cells
from vcmi_mapgen.core.placement.place import PlaceSpec, PlaceTarget, place_one
from vcmi_mapgen.core.planning.zone_index import ZoneRecord
from vcmi_mapgen.core.priors.gameplay import TerrainStats
from vcmi_mapgen.corpus.gameplay import load_gameplay

LOOT_ZONE_MAX_TILES = 60
_DIRS8 = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]

type _Cells = Sequence[tuple[int, int, bool]]
type _Spot = tuple[ZoneRecord, Tile]


def _nbs(t: Tile) -> Iterable[Tile]:
    return ((t[0] + dx, t[1] + dy) for dx, dy in _DIRS8)


def _find_entry_tile(
    interactive: Collection[Tile], footprint_cells: _Cells, ts: AbstractSet[Tile]
) -> Tile | None:
    footprint = {(cx, cy) for cx, cy, _blk in footprint_cells}
    passable_footprint = {(cx, cy) for cx, cy, blk in footprint_cells if not blk}
    frontier = set(interactive)
    visited = set(frontier)
    for _ in range(len(footprint) + 1):
        nxt: set[Tile] = set()
        for f in sorted(frontier):
            for nb in _nbs(f):
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
    footprint_cells: _Cells,
    ts: AbstractSet[Tile],
    all_ts: AbstractSet[Tile],
    blocked_ts: AbstractSet[Tile],
) -> bool:
    footprint = {(cx, cy) for cx, cy, _ in footprint_cells}
    ext_ts = all_ts - ts
    return any(
        nb in ext_ts and nb not in footprint and nb not in blocked_ts for nb in _nbs(entry_tile)
    )


def _reach8(seed_tiles: Iterable[Tile], avail: AbstractSet[Tile]) -> set[Tile]:
    return reach(avail, sorted({t for t in seed_tiles if t in avail}), _DIRS8)


def _path_prev(
    reached: AbstractSet[Tile], target: Tile, ts: AbstractSet[Tile], footprint: AbstractSet[Tile]
) -> dict[Tile, Tile] | None:
    prev: dict[Tile, Tile] = {}
    seen = set(reached)
    q = collections.deque(sorted(reached))
    while q:
        cur = q.popleft()
        if cur == target:
            return prev
        for nb in _nbs(cur):
            if nb in ts and nb not in footprint and nb not in seen:
                seen.add(nb)
                prev[nb] = cur
                q.append(nb)
    return None


def find_entry_corridor(
    entry_tile: Tile | None,
    footprint_cells: _Cells,
    ts: AbstractSet[Tile],
    all_ts: AbstractSet[Tile],
) -> set[Tile]:
    """The minimal set of ``ts`` tiles beyond ``entry_tile`` that stay unsealed so every
    interior tile connects to the access object. It grows one shortest path at a time."""
    if entry_tile is None:
        return set()
    footprint = {(cx, cy) for cx, cy, _ in footprint_cells}
    ext_ts = all_ts - ts
    boundary = {t for t in ts if any(nb in ext_ts for nb in _nbs(t))}
    interior = ts - boundary
    corridor = {entry_tile}
    reached = _reach8({entry_tile}, interior | corridor)
    skipped: set[Tile] = set()
    pending = interior - reached - skipped
    while pending:
        target = min(pending)
        prev = _path_prev(reached, target, ts, footprint)
        if prev is None:
            skipped.add(target)
        else:
            cur: Tile | None = target
            while cur is not None and cur not in reached:
                corridor.add(cur)
                cur = prev.get(cur)
            reached = _reach8({entry_tile}, interior | corridor)
        pending = interior - reached - skipped
    return corridor


def _count_clusters(boundary: AbstractSet[Tile]) -> int:
    seen: set[Tile] = set()
    n = 0
    for t in sorted(boundary):
        if t in seen:
            continue
        n += 1
        seen |= _reach8({t}, boundary)
    return n


def _passage_components(
    zr: ZoneRecord, all_ts: AbstractSet[Tile], blocked_ts: AbstractSet[Tile]
) -> tuple[int, frozenset[Tile]]:
    ts = zr.ts - blocked_ts
    ext_ts = (all_ts - zr.ts) - blocked_ts
    boundary = {t for t in ts if any(nb in ext_ts for nb in _nbs(t))}
    return _count_clusters(boundary), frozenset(boundary)


def _anchor_clear(cand: ZoneRecord, claims: AbstractSet[Tile], t: Tile) -> bool:
    tx, ty = t
    return all(
        c not in cand.ts or (c in cand.open_set and c not in claims)
        for c in ((tx - 1, ty - 1), (tx, ty - 1), (tx - 1, ty))
    )


def _cheb(a: Tile, b: Tile) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _try_guard_ring(ext_zr: ZoneRecord, ext_t: Tile, target: PlaceTarget, spec: PlaceSpec) -> bool:
    free = ext_zr.reach - target.cover.claims
    for t in sorted(free, key=lambda t: (_cheb(t, ext_t), t)):
        if _cheb(t, ext_t) > 1:
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
    def of(cls, ts: AbstractSet[Tile], pcx: float, pcy: float) -> Self:
        x0 = min(x for x, _ in ts)
        x1 = max(x for x, _ in ts)
        y0 = min(y for _, y in ts)
        y1 = max(y for _, y in ts)
        sides = [
            ("top", pcy - y0),
            ("bottom", y1 - pcy),
            ("left", pcx - x0),
            ("right", x1 - pcx),
        ]
        side = min(sides, key=itemgetter(1))[0]
        return cls(side, x0, x1, y0, y1, pcx, pcy)

    def score(self, t: Tile) -> tuple[float, float]:
        gx, gy = t
        if self.passage_side in ("top", "bottom"):
            bnd_y = self.bbox_y0 if self.passage_side == "top" else self.bbox_y1
            return (abs(gy - bnd_y), abs((gx - 1.5) - self.passage_cx))
        ideal_x = self.bbox_x0 + 3 if self.passage_side == "left" else self.bbox_x1
        return (abs(gy - self.passage_cy), abs(gx - ideal_x))


@dataclass(frozen=True, slots=True)
class LootAccess:
    """How a loot zone is entered: the inside tile next to the access object, the access
    object's footprint and its visit tiles."""

    entry: Tile
    footprint: frozenset[Tile]
    interactive: frozenset[Tile]


@dataclass(frozen=True, slots=True)
class _LootZone:
    zid: int
    terrain: str
    st: TerrainStats
    ts: frozenset[Tile]
    rng: random.Random
    ext_pools: tuple[list[ZoneRecord], ...]
    open_set: frozenset[Tile]
    reach: frozenset[Tile]


@dataclass(frozen=True, slots=True)
class _Sited:
    entry: Tile
    cells: _Cells
    interactive: frozenset[Tile]


@final
class GatedPlacer:
    """Picks the loot zones of one level and builds the gate or monolith access of each."""

    def __init__(
        self,
        catalog: Catalog,
        zone_records: Sequence[ZoneRecord],
        objs_existing: Sequence[PlacedObject],
        seed: int,
        bounds: tuple[int, int] | None,
    ) -> None:
        self.catalog = catalog
        self.zone_records = list(zone_records)
        self.objs_existing = list(objs_existing)
        self.seed = seed
        self.bounds = bounds
        self.town_tiles = {(o.x, o.y) for o in objs_existing if o.purpose == Purpose.TOWN}
        self.cover = CoverIndex(objs_existing)
        self.all_ts: frozenset[Tile] = frozenset().union(*(zr.ts for zr in zone_records))
        self.blocked = FP.blocking_cells(objs_existing)
        self.interactive_existing = {
            c for o in objs_existing for c in FP.interactive_cells(o.footprint, o.x, o.y)
        }
        self.purposeful = {
            (cx, cy)
            for o in objs_existing
            if o.purpose
            for cx, cy, _b in FP.anchored_cells(o.footprint, o.x, o.y)
        }
        self.zone_of = {t: zr for zr in zone_records for t in zr.ts}
        self.ext_no_castle: list[ZoneRecord] = []
        self.ext_any: list[ZoneRecord] = []
        self.placed_ext_tiles: list[Tile] = []
        self.objs: list[PlacedObject] = []
        self.n_placed = 0
        self.access: dict[int, LootAccess] = {}
        self.gate_count = 0
        self.mono_count = 0
        self._decor: dict[str, list[Identity]] = {}

    def run(self) -> tuple[list[PlacedObject], int, dict[int, LootAccess], frozenset[Tile]]:
        loot = self._loot_zones()
        loot_zids = {zr.zid for zr, _p in loot}
        self.ext_any = [zr for zr in self.zone_records if zr.zid not in loot_zids]
        self.ext_no_castle = [zr for zr in self.ext_any if not (zr.ts & self.town_tiles)]
        for zr in self.ext_any:
            self.cover.claim(zr.ts & self.blocked)
        for zr, passage in sorted(loot, key=lambda p: p[0].zid):
            self._process(zr, passage)
        return self.objs, self.n_placed, self.access, frozenset(self.cover.claims)

    def _eligible(self, zr: ZoneRecord) -> bool:
        return (
            len(zr.ts) <= LOOT_ZONE_MAX_TILES
            and not (zr.ts & self.town_tiles)
            and not (zr.ts & self.purposeful)
            and bool(zr.ts - self.blocked)
        )

    def _loot_zones(self) -> list[tuple[ZoneRecord, frozenset[Tile]]]:
        out: list[tuple[ZoneRecord, frozenset[Tile]]] = []
        for zr in self.zone_records:
            if not self._eligible(zr):
                continue
            n, boundary = _passage_components(zr, self.all_ts, self.blocked)
            if n == 1:
                out.append((zr, boundary))
        return out

    def _process(self, zr: ZoneRecord, passage: frozenset[Tile]) -> None:
        rng = random.Random(self.seed ^ (zr.zid * 92821) ^ 0xA117)
        walkable = zr.ts - self.blocked
        reach = frozenset(walkable - self.interactive_existing)
        self.cover.claim((zr.ts & self.blocked) | (zr.ts & self.interactive_existing))
        zone = _LootZone(
            zr.zid,
            zr.terrain,
            load_gameplay()[zr.terrain],
            zr.ts,
            rng,
            (self.ext_no_castle, self.ext_any),
            reach,
            reach,
        )
        pcx = sum(x for x, _ in passage) / len(passage)
        pcy = sum(y for _, y in passage) / len(passage)
        aim = _GateAim.of(zr.ts, pcx, pcy)
        mark = self.cover.mark()
        n_objs = len(self.objs)
        blocked = frozenset(self.blocked)
        use_gate = rng.random() < 0.5
        order = (True, False) if use_gate else (False, True)
        for gate in order:
            ok = self._place_gate(zone, aim) if gate else self._place_monolith(zone)
            if ok:
                return
            self.cover.rollback(mark)
            del self.objs[n_objs:]
            self.blocked = set(blocked)

    def _remoteness(self, x: float, y: float) -> float:
        d_town = min((math.dist((x, y), t) for t in self.town_tiles), default=1e9)
        d_ext = min((math.dist((x, y), t) for t in self.placed_ext_tiles), default=1e9)
        return d_town + d_ext

    def _far_score(self, zr: ZoneRecord) -> tuple[float, int]:
        free = zr.reach - self.cover.claims
        if not free:
            return (-1.0, 0)
        cx = sum(x for x, _ in zr.ts) / len(zr.ts)
        cy = sum(y for _, y in zr.ts) / len(zr.ts)
        return (self._remoteness(cx, cy), len(free))

    def _find_ext_spot(
        self, ident: Identity, pools: Iterable[Sequence[ZoneRecord]]
    ) -> _Spot | None:
        for pool in pools:
            spot = self._find_ext_spot_in(ident, pool)
            if spot is not None:
                return spot
        return None

    def _find_ext_spot_in(self, ident: Identity, pool: Sequence[ZoneRecord]) -> _Spot | None:
        rules = CellRules(bounds=self.bounds)
        for cand in sorted(pool, key=self._far_score, reverse=True):
            claims = self.cover.claims
            free = sorted(
                cand.reach - claims, key=lambda t: (self._remoteness(*t), t), reverse=True
            )
            for t in free:
                if not _anchor_clear(cand, claims, t):
                    continue
                if legal_cells(ident, t, cand.reach, claims, rules) is not None:
                    return cand, t
        return None

    def _in_bounds(self, cells: _Cells) -> bool:
        w, h = self.bounds if self.bounds is not None else (999, 999)
        return all(0 <= cx < w and 0 <= cy < h for cx, cy, _b in cells)

    def _gate_cells_fit(self, zone: _LootZone, cells: _Cells) -> bool:
        for cx, cy, blk in cells:
            if not blk and (cx, cy) in self.blocked:
                return False
            if blk and (cx, cy) not in zone.ts and not self._free_outside((cx, cy)):
                return False
        return True

    def _free_outside(self, t: Tile) -> bool:
        if t in self.blocked:
            return True
        nb_zr = self.zone_of.get(t)
        return nb_zr is None or t not in self.cover.claims

    def _commit_gate(self, gate_ident: Identity, g: Tile, cells: _Cells) -> bool:
        gate_obj = PlacedObject.at(gate_ident, g, purpose=Purpose.QUEST_GATE)
        if not self.cover.try_claim(gate_obj, [(cx, cy) for cx, cy, _b in cells]):
            return False
        self.objs.append(gate_obj)
        self.blocked |= {(cx, cy) for cx, cy, blk in cells if blk}
        return True

    def _site_gate(self, zone: _LootZone, aim: _GateAim, gate_ident: Identity) -> _Sited | None:
        for g in sorted(zone.ts, key=lambda t: (aim.score(t), t)):
            cells = list(FP.anchored_cells(gate_ident.footprint, *g))
            if not self._in_bounds(cells):
                continue
            interactive = FP.interactive_cells(gate_ident.footprint, *g)
            if not all(c in zone.open_set for c in interactive):
                continue
            if not self._gate_cells_fit(zone, cells):
                continue
            entry = _find_entry_tile(interactive, cells, zone.ts)
            if entry is None or _entry_tile_has_stray_leak(
                entry, cells, zone.ts, self.all_ts, self.blocked
            ):
                continue
            if self._commit_gate(gate_ident, g, cells):
                return _Sited(entry, cells, frozenset(interactive))
        return None

    def _has_ext_access(self, ts: AbstractSet[Tile], interactive: AbstractSet[Tile]) -> bool:
        blocked = FP.blocking_cells(self.objs) | self.blocked
        w, h = self.bounds if self.bounds is not None else (999, 999)
        return any(
            nb not in ts and nb not in blocked and 0 <= nb[0] < w and 0 <= nb[1] < h
            for c in interactive
            for nb in _nbs(c)
        )

    def _place_gate(self, zone: _LootZone, aim: _GateAim) -> bool:
        gates = self.catalog.border_gates()
        gate_ident, key_ident = gates[self.gate_count % len(gates)]
        km_spot = self._find_ext_spot(key_ident, zone.ext_pools)
        if km_spot is None:
            return False
        sited = self._site_gate(zone, aim, gate_ident)
        if sited is None or not self._has_ext_access(zone.ts, sited.interactive):
            return False
        self._seal(zone, sited)
        if not self._finish(zone, sited):
            return False
        if not self._place_ext_partner(zone.zid, km_spot, key_ident, Purpose.QUEST_GATE):
            return False
        self.gate_count += 1
        self._record_access(zone.zid, sited)
        return True

    def _site_monolith(self, zone: _LootZone, mono_ident: Identity) -> tuple[Tile, _Sited] | None:
        walkable = zone.ts - self.blocked
        comp_size: dict[Tile, int] = {}
        for t in sorted(walkable):
            if t not in comp_size:
                comp = _reach8({t}, walkable)
                comp_size.update(dict.fromkeys(comp, len(comp)))
        cx0 = sum(x for x, _ in zone.ts) / len(zone.ts)
        cy0 = sum(y for _, y in zone.ts) / len(zone.ts)
        rules = CellRules(bounds=self.bounds)
        cands = sorted(
            zone.reach - self.cover.claims,
            key=lambda c: (-comp_size.get(c, 0), (c[0] - cx0) ** 2 + (c[1] - cy0) ** 2, c),
        )
        for t in cands:
            fp_coords = legal_cells(mono_ident, t, zone.reach, self.cover.claims, rules)
            if fp_coords is None:
                continue
            mono_cells = list(FP.anchored_cells(mono_ident.footprint, *t))
            entry = _find_entry_tile(fp_coords, mono_cells, zone.ts)
            if entry is None or _entry_tile_has_stray_leak(
                entry, mono_cells, zone.ts, self.all_ts, self.blocked
            ):
                continue
            interactive = frozenset(FP.interactive_cells(mono_ident.footprint, *t))
            return t, _Sited(entry, mono_cells, interactive)
        return None

    def _target(self, zone: _LootZone) -> PlaceTarget:
        return PlaceTarget(
            self.catalog,
            self.objs,
            self.cover,
            zone.reach,
            zone.rng,
            zone.st,
            bounds=self.bounds,
        )

    def _place_monolith(self, zone: _LootZone) -> bool:
        portals = self.catalog.portals()
        mono_ident = portals[self.mono_count % len(portals)]
        spot = self._find_ext_spot(mono_ident, zone.ext_pools)
        if spot is None:
            return False
        found = self._site_monolith(zone, mono_ident)
        if found is None:
            return False
        int_t, sited = found
        n0 = len(self.objs)
        spec = PlaceSpec(Purpose.TRANSPORT, None, ident=mono_ident, interactive_only=True)
        if not place_one(self._target(zone), spec, *int_t):
            return False
        self.blocked |= FP.blocking_cells(self.objs[n0:])
        self._seal(zone, sited)
        if not self._finish(zone, sited):
            return False
        if not self._place_ext_partner(zone.zid, spot, mono_ident, Purpose.TRANSPORT):
            return False
        self.mono_count += 1
        self._record_access(zone.zid, sited)
        return True

    def _record_access(self, zid: int, sited: _Sited) -> None:
        footprint = frozenset((cx, cy) for cx, cy, _b in sited.cells)
        self.access[zid] = LootAccess(sited.entry, footprint, sited.interactive)

    def _decor_pool(self, terrain: str) -> list[Identity]:
        if terrain not in self._decor:
            self._decor[terrain] = self.catalog.decor(terrain, blocking=True, max_cells=1)
        return self._decor[terrain]

    def _seal_tile(self, t: Tile, terrain: str, rng: random.Random) -> bool:
        pool = self._decor_pool(terrain)
        if not pool:
            return False
        o = PlacedObject.at(rng.choice(pool), t, purpose="")
        if not self.cover.try_claim(o, [t]):
            return False
        self.blocked.add(t)
        self.objs.append(o)
        return True

    def _seal(self, zone: _LootZone, sited: _Sited) -> None:
        footprint = {(cx, cy) for cx, cy, _b in sited.cells}
        corridor = find_entry_corridor(sited.entry, sited.cells, zone.ts, self.all_ts)
        self._seal_all_passages(zone, sited.interactive | footprint | corridor)
        self._close_stray_leaks(zone, sited.interactive, footprint | corridor | {sited.entry})

    def _seal_all_passages(self, zone: _LootZone, skip: AbstractSet[Tile]) -> None:
        ext_ts = self.all_ts - zone.ts
        for t in sorted(zone.ts):
            if t in skip or t in self.cover.claims or t in self.blocked:
                continue
            if any(nb in ext_ts for nb in _nbs(t)):
                _ = self._seal_tile(t, zone.terrain, zone.rng)

    def _close_leak(self, zone: _LootZone, t: Tile, nb: Tile, keep: AbstractSet[Tile]) -> bool:
        nb_zr = self.zone_of.get(nb)
        if nb_zr is not None and nb not in self.cover.claims:
            _ = self._seal_tile(nb, nb_zr.terrain, zone.rng)
        if nb in self.blocked or t in keep or t in self.cover.claims:
            return False
        return self._seal_tile(t, zone.terrain, zone.rng)

    def _close_stray_leaks(
        self, zone: _LootZone, interactive: AbstractSet[Tile], keep: AbstractSet[Tile]
    ) -> None:
        ext_ts = self.all_ts - zone.ts
        for t in sorted(zone.ts):
            if t in interactive or t in self.blocked:
                continue
            for nb in _nbs(t):
                if nb not in ext_ts or nb in self.blocked:
                    continue
                if self._close_leak(zone, t, nb, keep):
                    break

    def _finish(self, zone: _LootZone, sited: _Sited) -> bool:
        walkable = (self.all_ts - self.blocked) - sited.interactive
        return _reach8({sited.entry}, walkable) <= zone.ts

    def _place_ext_partner(self, zid: int, spot: _Spot, ident: Identity, purpose: str) -> bool:
        ext_zr, ext_t = spot
        ext_rng = random.Random(self.seed ^ (zid * 131071) ^ 0xCEBF)
        target = PlaceTarget(
            self.catalog,
            self.objs,
            self.cover,
            ext_zr.reach,
            ext_rng,
            load_gameplay()[ext_zr.terrain],
            bounds=self.bounds,
        )
        n0 = len(self.objs)
        spec = PlaceSpec(purpose, None, ident=ident)
        if not place_one(target, spec, *ext_t) and not any(
            place_one(target, spec, *t) for t in sorted(ext_zr.reach - self.cover.claims)
        ):
            return False
        self.n_placed += 1
        self.placed_ext_tiles.append(ext_t)
        gident = self.catalog.guard(7)
        for clear_of in (FP.decor_blocking_cells(self.objs), None):
            if _try_guard_ring(
                ext_zr,
                ext_t,
                target,
                PlaceSpec(Purpose.GUARD, None, ident=gident, clear_of=clear_of),
            ):
                break
        self.blocked |= FP.blocking_cells(self.objs[n0:])
        return True


def place_gated_zones(
    catalog: Catalog,
    zone_records: Sequence[ZoneRecord],
    objs_existing: Sequence[PlacedObject],
    seed: int = 1,
    bounds: tuple[int, int] | None = None,
) -> tuple[list[PlacedObject], int, dict[int, LootAccess], frozenset[Tile]]:
    """Seal every eligible loot zone of one level behind a gate or a monolith pair. Returns
    the new objects, the number of access pairs, the access of each loot zone and the tiles
    the level has claimed."""
    return GatedPlacer(catalog, zone_records, objs_existing, seed, bounds).run()

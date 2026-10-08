"""Gated loot zones: a small zone with one passage gets sealed, and its only way in becomes a
Border Gate with its Keymaster outside, or a monolith pair."""

from __future__ import annotations

import collections
import math
import random
from collections.abc import Collection, Iterable, Iterator, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from operator import itemgetter
from typing import Self, final

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.reach import reach
from vcmi_mapgen.core.model import CoverIndex, Identity, PlacedObject, PlacementRule, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.placement.cells import CellRules, legal_cells
from vcmi_mapgen.core.placement.ground import Ground, stands
from vcmi_mapgen.core.placement.place import PlaceSpec, PlaceTarget, place_one
from vcmi_mapgen.core.planning.guarding import PrizeGuard
from vcmi_mapgen.core.planning.loot_zones import choose_loot_zones, passage
from vcmi_mapgen.core.planning.zone_index import ZoneRecord
from vcmi_mapgen.core.priors.gameplay import GameplayStats, TerrainStats
from vcmi_mapgen.core.steps.gated.result import LootAccess

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


def _anchor_clear(cand: ZoneRecord, claims: AbstractSet[Tile], t: Tile) -> bool:
    tx, ty = t
    return all(
        c not in cand.ts or (c in cand.open_set and c not in claims)
        for c in ((tx - 1, ty - 1), (tx, ty - 1), (tx - 1, ty))
    )


def _splits(before: AbstractSet[Tile], after: AbstractSet[Tile]) -> bool:
    label: dict[Tile, int] = {}
    for t in sorted(after):
        if t not in label:
            label.update(dict.fromkeys(_reach8({t}, after), len(label)))
    seen: set[Tile] = set()
    for t in sorted(before):
        if t in seen:
            continue
        comp = _reach8({t}, before)
        seen |= comp
        if len({label[c] for c in comp if c in label}) > 1:
            return True
    return False


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


@dataclass(frozen=True, slots=True)
class GatedLevel:
    """One level to seal: every zone record, the objects already on the level and the
    gameplay statistics per terrain, the rules every new object must pass and the level's
    terrain grid every seal must be allowed on. ``reached`` holds the tiles a home reaches on
    foot. A loot zone and the partner outside it stand only on those, and None reads as
    every tile. ``loot`` holds the zones chosen to seal, and None reads as the zones
    ``choose_loot_zones`` picks over the level as it stands."""

    zone_records: Sequence[ZoneRecord]
    objs: Sequence[PlacedObject]
    gameplay: GameplayStats
    rules: Sequence[PlacementRule] = ()
    ground: Ground = ()
    guard: PrizeGuard = field(default_factory=PrizeGuard)
    reached: AbstractSet[Tile] | None = None
    loot: AbstractSet[int] | None = None


@final
class GatedPlacer:
    """Picks the loot zones of one level and builds the gate or monolith access of each."""

    def __init__(
        self,
        catalog: Catalog,
        level: GatedLevel,
        seed: int,
        bounds: tuple[int, int] | None,
    ) -> None:
        zone_records, objs_existing = level.zone_records, level.objs
        self.catalog = catalog
        self.gameplay = level.gameplay
        self.guard = level.guard
        self.zone_records = list(zone_records)
        self.objs_existing = list(objs_existing)
        self.seed = seed
        self.bounds = bounds
        self.town_tiles = {(o.x, o.y) for o in objs_existing if o.purpose == Purpose.TOWN}
        self.cover = CoverIndex(objs_existing, rules=level.rules)
        self.ground = level.ground
        self.reached = level.reached
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
        self.chosen = (
            choose_loot_zones({zr.zid: zr.ts for zr in zone_records}, self.blocked, self.ground)
            if level.loot is None
            else level.loot
        )
        self.ext_no_castle: list[ZoneRecord] = []
        self.ext_any: list[ZoneRecord] = []
        self.placed_ext_tiles: list[Tile] = []
        self.objs: list[PlacedObject] = []
        self.n_placed = 0
        self.access: dict[int, LootAccess] = {}
        self.gate_count: int = 0
        self.mono_count: int = 0
        self._decor: dict[str, list[Identity]] = {}

    def run(self) -> tuple[list[PlacedObject], int, dict[int, LootAccess], frozenset[Tile]]:
        loot = self._loot_zones()
        loot_zids = {zr.zid for zr, _p in loot}
        self.ext_any = [
            zr for zr in self.zone_records if zr.zid not in loot_zids and self._reached(zr)
        ]
        self.ext_no_castle = [zr for zr in self.ext_any if not (zr.ts & self.town_tiles)]
        for zr in self.ext_any:
            self.cover.claim(zr.ts & self.blocked)
        for zr, way in sorted(loot, key=lambda p: p[0].zid):
            self._process(zr, way)
        return self.objs, self.n_placed, self.access, frozenset(self.cover.claims)

    def _reached(self, zr: ZoneRecord) -> bool:
        return self.reached is None or bool(zr.ts & self.reached)

    def _eligible(self, zr: ZoneRecord) -> bool:
        return (
            zr.zid in self.chosen
            and self._reached(zr)
            and not (zr.ts & self.town_tiles)
            and not (zr.ts & self.purposeful)
        )

    def _loot_zones(self) -> list[tuple[ZoneRecord, frozenset[Tile]]]:
        out: list[tuple[ZoneRecord, frozenset[Tile]]] = []
        for zr in self.zone_records:
            if not self._eligible(zr):
                continue
            n, boundary = passage(zr.ts, self.all_ts, self.blocked)
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
            self.gameplay[zr.terrain],
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
        counts = (self.n_placed, len(self.placed_ext_tiles), self.gate_count, self.mono_count)
        outside = self.all_ts - zr.ts
        use_gate = rng.random() < 0.5
        order = (True, False) if use_gate else (False, True)
        for gate in order:
            ok = self._place_gate(zone, aim) if gate else self._place_monolith(zone)
            if ok and not _splits(outside - blocked, outside - self.blocked):
                return
            self.n_placed, n_ext, self.gate_count, self.mono_count = counts
            del self.placed_ext_tiles[n_ext:]
            _ = self.access.pop(zr.zid, None)
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
        return next(self._ext_spots(ident, pools), None)

    def _ext_spots(self, ident: Identity, pools: Iterable[Sequence[ZoneRecord]]) -> Iterator[_Spot]:
        rules = CellRules(bounds=self.bounds)
        for pool in pools:
            for cand in sorted(pool, key=self._far_score, reverse=True):
                claims = self.cover.claims
                free = sorted(
                    cand.reach - claims, key=lambda t: (self._remoteness(*t), t), reverse=True
                )
                for t in free:
                    if not _anchor_clear(cand, claims, t):
                        continue
                    if legal_cells(ident, t, cand.reach, claims, rules) is not None:
                        yield cand, t

    def _in_bounds(self, cells: _Cells) -> bool:
        w, h = self.bounds if self.bounds is not None else (999, 999)
        return all(0 <= cx < w and 0 <= cy < h for cx, cy, _b in cells)

    def _gate_cells_fit(
        self, zone: _LootZone, cells: _Cells, interactive: AbstractSet[Tile]
    ) -> bool:
        for cx, cy, blk in cells:
            if (cx, cy) in interactive and (cx, cy) in self.blocked:
                return False
            if blk and (cx, cy) not in zone.ts and not self._free_outside((cx, cy)):
                return False
        return True

    def _free_outside(self, t: Tile) -> bool:
        if t in self.blocked:
            return True
        nb_zr = self.zone_of.get(t)
        return nb_zr is None or t not in self.cover.claims

    def _commit_gate(
        self, gate_ident: Identity, g: Tile, cells: _Cells, interactive: AbstractSet[Tile]
    ) -> bool:
        gate_obj = PlacedObject.at(gate_ident, g, purpose=Purpose.QUEST_GATE)
        solid = [(cx, cy) for cx, cy, blk in cells if blk or (cx, cy) in interactive]
        if not self.cover.try_claim(gate_obj, solid):
            return False
        self.objs.append(gate_obj)
        self.blocked |= {(cx, cy) for cx, cy, blk in cells if blk}
        return True

    def _gate_sites(
        self, zone: _LootZone, aim: _GateAim, gate_ident: Identity
    ) -> Iterator[tuple[Tile, _Sited]]:
        for g in sorted(zone.ts, key=lambda t: (aim.score(t), t)):
            cells = list(FP.anchored_cells(gate_ident.footprint, *g))
            if not self._in_bounds(cells):
                continue
            interactive = frozenset(FP.interactive_cells(gate_ident.footprint, *g))
            if not all(c in zone.open_set for c in interactive):
                continue
            if not self._gate_cells_fit(zone, cells, interactive):
                continue
            entry = _find_entry_tile(interactive, cells, zone.ts)
            if entry is None or _entry_tile_has_stray_leak(
                entry, cells, zone.ts, self.all_ts, self.blocked
            ):
                continue
            solid = frozenset((cx, cy) for cx, cy, blk in cells if blk)
            if self._doorstep(zone.ts, interactive, solid):
                yield g, _Sited(entry, cells, interactive)

    def _doorstep(
        self, ts: AbstractSet[Tile], interactive: AbstractSet[Tile], extra: AbstractSet[Tile]
    ) -> frozenset[Tile]:
        blocked = FP.blocking_cells(self.objs) | self.blocked | extra
        w, h = self.bounds if self.bounds is not None else (999, 999)
        return frozenset(
            nb
            for c in interactive
            for nb in _nbs(c)
            if nb not in ts
            and nb not in blocked
            and nb in self.all_ts
            and 0 <= nb[0] < w
            and 0 <= nb[1] < h
        )

    def _place_gate(self, zone: _LootZone, aim: _GateAim) -> bool:
        gates = self.catalog.border_gates()
        gate_ident, key_ident = gates[self.gate_count % len(gates)]
        if self._find_ext_spot(key_ident, zone.ext_pools) is None:
            return False
        sited = self._seal_gate(zone, aim, gate_ident)
        if sited is None:
            return False
        if not self._place_ext_partner(zone.zid, zone.ext_pools, key_ident, Purpose.QUEST_GATE):
            return False
        self.gate_count += 1
        self._record_access(zone.zid, sited)
        return True

    def _seal_gate(self, zone: _LootZone, aim: _GateAim, gate_ident: Identity) -> _Sited | None:
        mark = self.cover.mark()
        n0 = len(self.objs)
        blocked = set(self.blocked)
        for g, sited in self._gate_sites(zone, aim, gate_ident):
            for keep_doorstep in (True, False):
                if self._commit_gate(gate_ident, g, sited.cells, sited.interactive):
                    doorstep = self._doorstep(zone.ts, sited.interactive, frozenset())
                    self._seal(zone, sited, doorstep if keep_doorstep else frozenset())
                    if self._finish(zone, sited) and self._doorstep(
                        zone.ts, sited.interactive, frozenset()
                    ):
                        return sited
                self.cover.rollback(mark)
                del self.objs[n0:]
                self.blocked = set(blocked)
        return None

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
        self._seal(zone, sited, frozenset())
        if not self._finish(zone, sited):
            return False
        if not self._place_ext_partner(zone.zid, zone.ext_pools, mono_ident, Purpose.TRANSPORT):
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
        pool = [i for i in self._decor_pool(terrain) if stands(self.catalog, i, t, self.ground)]
        if not pool:
            return False
        o = PlacedObject.at(rng.choice(pool), t, purpose="")
        if not self.cover.try_claim(o, [t]):
            return False
        self.blocked.add(t)
        self.objs.append(o)
        return True

    def _seal(self, zone: _LootZone, sited: _Sited, doorstep: AbstractSet[Tile]) -> None:
        footprint = {(cx, cy) for cx, cy, _b in sited.cells}
        corridor = find_entry_corridor(sited.entry, sited.cells, zone.ts, self.all_ts)
        self._seal_all_passages(zone, sited.interactive | footprint | corridor)
        keep = footprint | corridor | {sited.entry}
        self._close_stray_leaks(zone, sited.interactive, keep, doorstep)

    def _seal_all_passages(self, zone: _LootZone, skip: AbstractSet[Tile]) -> None:
        ext_ts = self.all_ts - zone.ts
        for t in sorted(zone.ts):
            if t in skip or t in self.cover.claims or t in self.blocked:
                continue
            if any(nb in ext_ts for nb in _nbs(t)):
                _ = self._seal_tile(t, zone.terrain, zone.rng)

    def _close_leak(
        self,
        zone: _LootZone,
        t: Tile,
        nb: Tile,
        keep: AbstractSet[Tile],
        doorstep: AbstractSet[Tile],
    ) -> bool:
        nb_zr = self.zone_of.get(nb)
        if nb_zr is not None and nb not in self.cover.claims and nb not in doorstep:
            _ = self._seal_tile(nb, nb_zr.terrain, zone.rng)
        if nb in self.blocked or t in keep or t in self.cover.claims:
            return False
        return self._seal_tile(t, zone.terrain, zone.rng)

    def _close_stray_leaks(
        self,
        zone: _LootZone,
        interactive: AbstractSet[Tile],
        keep: AbstractSet[Tile],
        doorstep: AbstractSet[Tile],
    ) -> None:
        ext_ts = self.all_ts - zone.ts
        for t in sorted(zone.ts):
            if t in interactive or t in self.blocked:
                continue
            for nb in _nbs(t):
                if nb not in ext_ts or nb in self.blocked:
                    continue
                if self._close_leak(zone, t, nb, keep, doorstep):
                    break

    def _finish(self, zone: _LootZone, sited: _Sited) -> bool:
        walkable = (self.all_ts - self.blocked) - sited.interactive
        return _reach8({sited.entry}, walkable) <= zone.ts

    def _place_ext_partner(
        self, zid: int, pools: Iterable[Sequence[ZoneRecord]], ident: Identity, purpose: str
    ) -> bool:
        ext_rng = random.Random(self.seed ^ (zid * 131071) ^ 0xCEBF)
        gident = self.catalog.guard(self.guard.level(ext_rng, zid))
        spec = PlaceSpec(purpose, None, ident=ident)
        mark = self.cover.mark()
        n0 = len(self.objs)
        for ext_zr, ext_t in self._ext_spots(ident, pools):
            target = PlaceTarget(
                self.catalog,
                self.objs,
                self.cover,
                ext_zr.reach,
                ext_rng,
                self.gameplay[ext_zr.terrain],
                bounds=self.bounds,
            )
            if place_one(target, spec, *ext_t) and self._guard_partner(ext_zr, target, n0, gident):
                self.n_placed += 1
                self.placed_ext_tiles.append(ext_t)
                self.blocked |= FP.blocking_cells(self.objs[n0:])
                return True
            self.cover.rollback(mark)
            del self.objs[n0:]
        return False

    def _guard_partner(
        self, ext_zr: ZoneRecord, target: PlaceTarget, n0: int, gident: Identity
    ) -> bool:
        partner = self.objs[n0]
        visit = FP.interactive_cells(partner.footprint, partner.x, partner.y)
        return any(
            _try_guard_ring(
                ext_zr, t, target, PlaceSpec(Purpose.GUARD, None, ident=gident, clear_of=clear_of)
            )
            for clear_of in (FP.decor_blocking_cells(self.objs), None)
            for t in visit
        )


def place_gated_zones(
    catalog: Catalog,
    level: GatedLevel,
    seed: int = 1,
    bounds: tuple[int, int] | None = None,
) -> tuple[list[PlacedObject], int, dict[int, LootAccess], frozenset[Tile]]:
    """Seal every eligible loot zone of one level behind a gate or a monolith pair. Returns
    the new objects, the number of access pairs, the access of each loot zone and the tiles
    the level has claimed."""
    return GatedPlacer(catalog, level, seed, bounds).run()

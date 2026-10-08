"""Portal rescue of unreachable zones and the target reachability check."""

import random
from collections.abc import Container, Mapping, Sequence
from dataclasses import dataclass, field
from functools import partial
from typing import final

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.geometry import centre_key
from vcmi_mapgen.core.grid.reach import STEPS8, land_reach, reach
from vcmi_mapgen.core.model import CoverIndex, Guard, Identity, PlacedObject, Tile, Zone
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.placement.guards import GAP, Clearance, Fit, fits
from vcmi_mapgen.core.planning.guarding import PrizeGuard
from vcmi_mapgen.core.planning.zone_index import ZoneRecord, bare_record
from vcmi_mapgen.core.priors.gameplay import GameplayStats

MIN_AREA = 25  # matches GameplayStep's own zone floor


def _walk_and_hard_cells(objs: Sequence[PlacedObject]) -> tuple[set[Tile], set[Tile]]:
    walk: set[Tile] = set()
    hard: set[Tile] = set()
    for o in objs:
        soft = o.purpose in (Purpose.RESOURCE_PILE, Purpose.REWARD_PICKUP, Purpose.GUARD)
        for cx, cy, blk in FP.anchored_cells(o.footprint, o.x, o.y):
            if blk and not soft:
                (hard if o.purpose else walk).add((cx, cy))
    return walk, hard


def unreachable_targets(
    size: int,
    grid: Sequence[Sequence[int]],
    objs: Sequence[PlacedObject],
    targets: Sequence[Tile],
) -> list[Tile]:
    """Targets a hero on foot cannot reach from the first open target.

    Guards and pickups count as passable, since a hero fights or collects them. Vegetation
    and every other object blocks. A target that no land path could reach even through
    vegetation sits on another island and is left out, because a boat or portal serves it."""
    land = {(x, y) for y in range(size) for x in range(size) if grid[y][x] < 8}
    walk, hard = _walk_and_hard_cells(objs)
    open_set = land - walk - hard
    targets_in = [t for t in targets if t in open_set]
    if not targets_in:
        return []
    root = targets_in[0]
    seen = reach(open_set, [root], STEPS8)
    bad = [t for t in targets_in if t not in seen]
    if not bad:
        return []
    through_veg = land - hard
    through = reach(through_veg, [root], STEPS8)
    return [t for t in bad if t in through]


PORTAL_MIN_AREA = 12  # smallest unreachable zone worth a portal rescue (mapeval's zone
#                        floor); smaller slivers keep the decoration-fill fate.
MAX_PORTALS = 8  # cap on rescued zones per map


@dataclass(slots=True)
class _LevelState:
    occupied: set[Tile]
    near: set[Tile]
    reserved: set[Tile]


def _outskirts_key(t: Tile, towns: Sequence[Tile]) -> tuple[float, Tile]:
    return (-min((t[0] - tx) ** 2 + (t[1] - ty) ** 2 for tx, ty in towns), t)


@dataclass(frozen=True, slots=True)
class PortalWorld:
    size: int
    grids: Mapping[int, Sequence[Sequence[int]]]
    zones_by_level: Mapping[int, Mapping[int, Zone]]
    objs_by_level: Mapping[int, list[PlacedObject]]
    targets_by_level: Mapping[int, list[Tile]]
    zone_records_by_level: Mapping[int, Sequence[ZoneRecord]]
    covers: Mapping[int, CoverIndex]
    gameplay: GameplayStats
    guards: Mapping[int, PrizeGuard] = field(default_factory=dict[int, PrizeGuard])


def check_reach(world: PortalWorld) -> None:
    """Raise ``ValueError`` when a level still has a target a hero on foot cannot reach."""
    for level in sorted(world.grids):
        cut = unreachable_targets(
            world.size,
            world.grids[level],
            world.objs_by_level[level],
            world.targets_by_level[level],
        )
        if cut:
            raise ValueError(
                f"PortalStep: L{level} has {len(cut)} target(s) cut off on foot, first {cut[0]}"
            )


@dataclass(frozen=True, slots=True)
class _Enclave:
    lvl: int
    zid: int
    terrain: str
    ts: set[Tile]
    cx: float
    cy: float


def _portal_end(lvl: int, ident: Identity, node: Tile) -> PlacedObject:
    return PlacedObject.at(ident, node, level=lvl, purpose=Purpose.TRANSPORT)


def _level_state(objs: Sequence[PlacedObject], targets: Sequence[Tile]) -> _LevelState:
    game_cells: set[Tile] = set()
    veg_blk: set[Tile] = set()
    for o in objs:
        cells = list(FP.anchored_cells(o.footprint, o.x, o.y))
        if not o.purpose:
            veg_blk.update((cx, cy) for cx, cy, b in cells if b)
        else:
            game_cells.update((cx, cy) for cx, cy, _b in cells)
    near = set(veg_blk)
    for cx, cy in game_cells:
        for gx in range(-GAP, GAP + 1):
            for gy in range(-GAP, GAP + 1):
                near.add((cx + gx, cy + gy))
    return _LevelState(
        occupied=game_cells | veg_blk,
        near=near,
        reserved=set(targets),
    )


@dataclass(frozen=True, slots=True)
class Rescued:
    """A zone a portal pair now opens: its level, its record and the tile a hero steps onto
    when the far portal lands it there."""

    level: int
    record: ZoneRecord
    entry: Tile


@dataclass(frozen=True, slots=True)
class Departure:
    """Where the rescue walks from: the start tile with its level, the open gate tiles a hero
    passes, and the zones an earlier step already priced, as (level, zone id)."""

    start: tuple[int, Tile]
    gate_xy: Container[Tile] = frozenset[Tile]()
    priced: Container[tuple[int, int]] = ()


def rescue_unreachable_zones(
    catalog: Catalog, world: PortalWorld, departure: Departure, seed: int
) -> list[Rescued]:
    """Unreachable zones become portal places instead of dead map area. Every land zone no
    walking path from the start town reaches, and no earlier step priced, gets a two-way
    monolith pair: the far end inside the zone on the legal tile nearest its centroid, the
    near end in the closest reachable zone on the same level, pushed toward that zone's
    outskirts, with a hostile guard beside it. The portal
    approaches land in ``targets``. Mutates ``objs_by_level``, ``targets_by_level`` and
    ``covers`` in place, and returns every rescued zone for its prizes."""

    reached = land_reach(world.grids, departure.gate_xy, [departure.start])
    cands = _candidates(catalog, world, reached, departure.priced)
    if not cands:
        return []
    return _PortalRescue(catalog, world, reached, seed).run(cands)


def _candidates(
    catalog: Catalog,
    world: PortalWorld,
    reached: Container[tuple[int, int, int]],
    priced: Container[tuple[int, int]],
) -> list[tuple[int, int, int, str]]:
    cands: list[tuple[int, int, int, str]] = []
    for lvl in sorted(world.zones_by_level):
        for zid, z in sorted(world.zones_by_level[lvl].items()):
            if z.terrain_type.is_barrier or z.area < PORTAL_MIN_AREA:
                continue
            terrain = catalog.terrain_name(z.terrain_type)
            ts = set(z.tiles_set)
            if (lvl, zid) in priced or any((x, y, lvl) in reached for (x, y) in ts):
                continue
            cands.append((-z.area, lvl, zid, terrain))
    cands.sort()
    return cands


@final
class _PortalRescue:
    def __init__(
        self,
        catalog: Catalog,
        world: PortalWorld,
        reached: Container[tuple[int, int, int]],
        seed: int,
    ) -> None:
        self.catalog = catalog
        self.world = world
        self.reached = reached
        self.seed = seed
        self.state: dict[int, _LevelState] = {}
        for lvl, objs in world.objs_by_level.items():
            self.state[lvl] = _level_state(objs, world.targets_by_level[lvl])

        self.zr_by: dict[int, dict[int, ZoneRecord]] = {
            lvl: {zr.zid: zr for zr in (world.zone_records_by_level.get(lvl) or ())}
            for lvl in world.zones_by_level
        }
        self.towns: dict[int, list[Tile]] = {
            lvl: [(o.x, o.y) for o in objs if o.purpose == Purpose.TOWN]
            for lvl, objs in world.objs_by_level.items()
        }

        self.cover_by = world.covers

    def _emit_end(self, lvl: int, ident: Identity, node: Tile, fit: Fit) -> Tile:
        allc, _blk, approach = fit
        end = _portal_end(lvl, ident, node)
        self.cover_by[lvl].add(end)
        self.world.objs_by_level[lvl].append(end)
        st = self.state[lvl]
        st.occupied.update(allc)
        for cx, cy in allc:
            for gx in range(-GAP, GAP + 1):
                for gy in range(-GAP, GAP + 1):
                    st.near.add((cx + gx, cy + gy))
        st.reserved.add(approach)
        self.world.targets_by_level[lvl].append(approach)
        return approach

    def _guard_spot(
        self, lvl: int, visit: Tile, appr: Tile, own_cells: Container[Tile], gident: Identity
    ) -> Tile | None:
        """First legal tile Chebyshev-1 from the near end's visitable cell, off its approach
        (a monster's zone of control covers all 8 neighbours, so stepping INTO the portal or
        out of it forces the fight); None when the surroundings can't seat one."""
        grid = self.world.grids[lvl]
        st = self.state[lvl]
        W = H = self.world.size
        for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (-1, 1), (1, -1), (-1, -1)):
            g = (visit[0] + dx, visit[1] + dy)
            if (
                not (0 <= g[0] < W and 0 <= g[1] < H)
                or Terrain(grid[g[1]][g[0]]).is_barrier
                or g == appr
                or g in st.occupied
                or g in own_cells
                or g in st.reserved
            ):
                continue
            if all(
                0 <= gx < W
                and 0 <= gy < H
                and Terrain(grid[gy][gx]).is_land
                and (gx, gy) not in st.occupied
                and (gx, gy) not in own_cells
                for gx, gy in FP.interactive_cells(gident.footprint, g[0], g[1])
            ):
                return g
        return None

    def run(self, cands: Sequence[tuple[int, int, int, str]]) -> list[Rescued]:
        n_placed = 0
        rescued: list[Rescued] = []
        for _na, lvl, zid, terrain in cands:
            if n_placed >= MAX_PORTALS:
                print(
                    f"  portals: cap {MAX_PORTALS} reached, "
                    + f"{len(cands) - n_placed} unreachable zone(s) left decoration-filled"
                )
                break
            found = self._rescue(lvl, zid, terrain, n_placed)
            if found is None:
                continue
            n_placed += 1
            rescued.append(found)
        return rescued

    def _far_end(self, zone: _Enclave, ident: Identity) -> tuple[Tile, Fit] | None:
        """The far portal's anchor: spaced from every gameplay object when the zone has room,
        else on any free ground whose approach joins the zone's walkable web."""
        st = self.state[zone.lvl]
        order = sorted(zone.ts, key=partial(centre_key, cx=zone.cx, cy=zone.cy))
        web = self._record(zone).passable
        spaced = Clearance(st.occupied, st.near, st.reserved)
        crowded = Clearance(st.occupied, st.occupied, st.reserved)
        for clear, joins in ((spaced, None), (crowded, web)):
            for t in order:
                fit = fits(ident, t, zone.ts, clear)
                if not fit or (joins is not None and fit[2] not in joins):
                    continue
                if self.cover_by[zone.lvl].accepts(_portal_end(zone.lvl, ident, t)):
                    return t, fit
        return None

    def _hosts(self, zone: _Enclave) -> list[tuple[float, int, int]]:
        lvl = zone.lvl
        hosts: list[tuple[float, int, int]] = []
        for hzid, hz in sorted(self.world.zones_by_level[lvl].items()):
            if hzid == zone.zid or hz.terrain_type.is_barrier:
                continue
            if hz.area < MIN_AREA:
                continue
            if not any((x, y, lvl) in self.reached for (x, y) in hz.tiles_set):
                continue
            hx, hy = hz.centroid
            hosts.append(((hx - zone.cx) ** 2 + (hy - zone.cy) ** 2, -hz.area, hzid))
        hosts.sort()
        return hosts

    def _near_in_host(
        self, zone: _Enclave, hzid: int, ident: Identity, gident: Identity
    ) -> tuple[Tile, Fit, Tile] | None:
        lvl = zone.lvl
        st = self.state[lvl]
        hts = set(self.world.zones_by_level[lvl][hzid].tiles_set)
        tl = self.towns[lvl]
        if tl:  # outskirts: value sits outward
            order = sorted(hts, key=partial(_outskirts_key, towns=tl))
        else:
            order = sorted(hts, key=partial(centre_key, cx=zone.cx, cy=zone.cy))

        for t in order:
            fit = fits(ident, t, hts, Clearance(st.occupied, st.near, st.reserved))
            if fit is None or not self.cover_by[lvl].accepts(_portal_end(lvl, ident, t)):
                continue
            visit = FP.interactive_cells(ident.footprint, t[0], t[1])[0]
            g = self._guard_spot(lvl, visit, fit[2], set(fit[0]), gident)
            if g is None:  # a portal must be guardable — skip
                continue  # candidates with no room for the guard
            return t, fit, g
        return None

    def _near_end(
        self,
        zone: _Enclave,
        ident: Identity,
        gident: Identity,
        hosts: Sequence[tuple[float, int, int]],
    ) -> tuple[Tile, Fit, Tile] | None:
        for _d, _ha, hzid in hosts[:3]:
            near = self._near_in_host(zone, hzid, ident, gident)
            if near:
                return near
        return None

    def _record(self, zone: _Enclave) -> ZoneRecord:
        zr = self.zr_by[zone.lvl].get(zone.zid)
        if zr is not None:
            return zr
        free = frozenset(zone.ts) - self.state[zone.lvl].occupied
        return bare_record(zone.zid, zone.terrain, frozenset(zone.ts), free)

    def _rescue(self, lvl: int, zid: int, terrain: str, n_placed: int) -> Rescued | None:
        z = self.world.zones_by_level[lvl][zid]
        ts = set(z.tiles_set)
        st = self.state[lvl]
        portals = self.catalog.portals()
        ident = portals[n_placed % len(portals)]
        cx, cy = z.centroid
        zone = _Enclave(lvl=lvl, zid=zid, terrain=terrain, ts=ts, cx=cx, cy=cy)

        far = self._far_end(zone, ident)
        if far is None:
            return None
        far_node, far_fit = far

        hosts = self._hosts(zone)

        guard_rng = random.Random(self.seed ^ (lvl * 7919) ^ (zid * 104729) ^ 0x6A4D)
        prize_guard = self.world.guards.get(lvl, PrizeGuard())
        gident = self.catalog.guard(prize_guard.level(guard_rng, zid))
        near = self._near_end(zone, ident, gident, hosts)
        if near is None:
            return None
        near_node, near_fit, gtile = near

        guard = PlacedObject.at(
            gident,
            gtile,
            level=lvl,
            purpose=Purpose.GUARD,
            payload=Guard(),
        )
        far_appr = self._emit_end(lvl, ident, far_node, far_fit)
        _ = self._emit_end(lvl, ident, near_node, near_fit)
        if not self.cover_by[lvl].try_add(guard):
            return None
        self.world.objs_by_level[lvl].append(guard)
        st.occupied.add(gtile)

        self.cover_by[lvl].claim((*far_fit[1], far_appr))
        return Rescued(lvl, self._record(zone), far_appr)

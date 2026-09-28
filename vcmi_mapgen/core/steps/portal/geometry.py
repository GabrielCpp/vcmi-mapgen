"""Portal rescue of unreachable zones and the target reachability check."""

import collections
import random
from collections.abc import Container, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from typing import final

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import CoverIndex, Identity, PlacedObject, Tile, Zone, ZoneRecord
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.steps.gameplay.mines import load_gameplay
from vcmi_mapgen.core.steps.gate.gates import GAP, Clearance, Fit, fits, rnd_monster
from vcmi_mapgen.core.steps.placement import PlaceSpec, PlaceTarget, place_one

MIN_AREA = 25  # matches GameplayStep's own zone floor


def _bfs8(open_set: Container[Tile], root: Tile) -> set[Tile]:
    seen = {root}
    queue = collections.deque([root])
    while queue:
        x, y = queue.popleft()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                n = (x + dx, y + dy)
                if n in open_set and n not in seen:
                    seen.add(n)
                    queue.append(n)
    return seen


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
    seen = _bfs8(open_set, root)
    bad = [t for t in targets_in if t not in seen]
    if not bad:
        return []
    through_veg = land - hard
    reach = _bfs8(through_veg, root)
    return [t for t in bad if t in reach]


def _entry_reach(passable: Container[Tile], entry: Tile) -> set[Tile]:
    reach: set[Tile] = {entry} if entry in passable else set()
    q = [entry]
    while q:
        x, y = q.pop()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if n in passable and n not in reach:
                reach.add(n)
                q.append(n)
    return reach


@dataclass(frozen=True, slots=True)
class RewardSite:
    """Where a reward hoard goes: the rescued zone's record, the portal's entry tile,
    the map bounds and the level's cover index."""

    zr: ZoneRecord
    entry: Tile
    bounds: tuple[int, int] | None = None
    cover: CoverIndex | None = None


def place_reward_zone(catalog: Catalog, site: RewardSite, seed: int = 1) -> list[PlacedObject]:
    """SPECIAL REWARD upgrade for a zone rescued by a guarded two-way monolith (pp_map's
    unreachable-zone pass): the pocket-cache grammar scaled to the whole zone — dense
    resource piles (all `cache`-tagged) reachable from the portal's `entry` tile, plus one
    interior guard whose strength tracks the accumulated value (the cache ladder + 1).
    Resources only — an artifact pickup used to be part of this hoard, but artifacts are
    pocket/loot-zone only now (a portal-rescued zone is neither), so those slots are
    additional resource piles instead; same total item count, same guard mechanic. Works
    both for fully-populated zones (extra richness) and for bare sub-MIN_AREA slivers the
    level pass skipped (their only content). Claims its cells in `zr.used` so the later
    pocket-cache pass never double-stacks. Returns objs."""
    zr, entry, bounds, cover = site.zr, site.entry, site.bounds, site.cover
    terrain = zr.terrain
    st = load_gameplay()[terrain]
    rng = random.Random(seed ^ (entry[0] * 92821) ^ (entry[1] * 131071) ^ 0x907A1)
    ts = zr.ts
    used = zr.used
    area = len(ts)

    # reach: what the portal's entry tile actually opens up (4-connected within passable)
    reach = _entry_reach(zr.passable, entry)
    if not reach:
        return []

    n_res = max(4, area // 10) + max(2, area // 25)
    pool_res = catalog.candidates(Purpose.RESOURCE_PILE, terrain)
    objs: list[PlacedObject] = []
    val = 0

    spots = sorted(reach - used)
    rng.shuffle(spots)
    for t in spots:
        if n_res <= 0:
            break
        if place_one(
            PlaceTarget(catalog, objs, used, reach, rng, st, bounds=bounds, cover=cover),
            PlaceSpec(Purpose.RESOURCE_PILE, pool_res, cache=True),
            t[0],
            t[1],
        ):
            n_res -= 1
            val += 2

    if objs:
        # one interior guard near the zone's own centre: the portal guard gates entry, this
        # one gates the hoard itself — cache ladder (pp_pickup pocket convention) + 1
        cx = sum(x for x, _ in ts) / area
        cy = sum(y for _, y in ts) / area
        lvl = 1 + (val >= 4) + (val >= 7) + (val >= 10) + (val >= 13) + 1
        gident = rnd_monster(catalog, lvl)
        for t in sorted(reach - used, key=partial(_centre_key, cx=cx, cy=cy)):
            if place_one(
                PlaceTarget(catalog, objs, used, reach, rng, st, bounds=bounds, cover=cover),
                PlaceSpec(Purpose.GUARD, None, ident=gident),
                t[0],
                t[1],
            ):
                break
    return objs


PORTAL_MIN_AREA = 12  # smallest unreachable zone worth a portal rescue (mapeval's zone
#                        floor); smaller slivers keep the decoration-fill fate.
MAX_PORTALS = 8  # cap on rescued zones per map
PORTAL_ANIMS = ("avxmn2g0", "avxmn2o0", "avxmn2p0", "avxmn4b0")
#                walk-on two-way monoliths (masks VV/VA, V/A — no blocking cells), subtypes
#                monolith1..4. Both ends of a pair share the animation, hence the subtype;
#                H3 networks ALL same-subtype ends, so a 5th+ portal reuses a subtype and
#                simply joins that network — still fully reachable, still relationally
#                complete (mapeval needs >=2 ends per subtype).


@dataclass(slots=True)
class _LevelState:
    occupied: set[Tile]
    near: set[Tile]
    reserved: set[Tile]


def _centre_key(t: Tile, cx: float, cy: float) -> tuple[float, Tile]:
    return ((t[0] - cx) ** 2 + (t[1] - cy) ** 2, t)


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


def _terrain_reach(
    grids: Mapping[int, Sequence[Sequence[int]]],
    gate_xy: Container[Tile],
    start: tuple[int, Tile],
) -> set[tuple[int, int, int]]:
    """BFS over LAND TERRAIN ONLY (objects deliberately ignored: an area merely sealed by
    vegetation is g2-repairable and NOT a portal candidate — only water/rock enclosure is
    truly unreachable), teleporting across subterranean-gate coordinates the way
    `traverse._gate_links` pairs them. Returns the reached (x, y, level) set."""
    lvl0, (sx, sy) = start
    reached: set[tuple[int, int, int]] = set()
    if grids.get(lvl0) is not None and Terrain(grids[lvl0][sy][sx]).is_land:
        reached = {(sx, sy, lvl0)}
    q = collections.deque(reached)
    H = len(grids[lvl0])
    W = len(grids[lvl0][0])
    while q:
        x, y, lvl = q.popleft()
        if (x, y) in gate_xy:
            for l2, g2 in grids.items():
                if l2 != lvl and Terrain(g2[y][x]).is_land and (x, y, l2) not in reached:
                    reached.add((x, y, l2))
                    q.append((x, y, l2))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if (
                0 <= nx < W
                and 0 <= ny < H
                and Terrain(grids[lvl][ny][nx]).is_land
                and (nx, ny, lvl) not in reached
            ):
                reached.add((nx, ny, lvl))
                q.append((nx, ny, lvl))
    return reached


def rescue_unreachable_zones(
    catalog: Catalog,
    world: PortalWorld,
    start: tuple[int, Tile],
    gate_xy: Container[Tile],
    seed: int,
) -> int:
    """Unreachable zones become SPECIAL REWARD zones behind a guarded portal (user-mandated:
    a portal makes a zone special) instead of dead map area. For every land zone no walking
    path from the start town can reach (terrain-level BFS — vegetation ignored, coastal L0
    zones exempt as boat-reachable, same policy as g2), place a two-way monolith pair: the
    FAR end inside the zone (nearest-to-centroid legal tile), the NEAR end in the closest
    reachable zone on the same level (pushed toward that zone's outskirts — descending
    distance-to-town, matching the corpus value-outward gradient) with a hostile guard
    adjacent to it, then upgrade the zone's loot via `place_reward_zone`.

    Runs AFTER both levels' zone passes and BEFORE the per-level repair/finish pass: the
    portal approaches and rewards land in `targets`, so `fill_open_islands` sees the zone's
    open component as target-holding and leaves it alone (previously it was blindly filled
    with decoration), and `traverse`'s monolith-network links count it reachable. Mutates
    `objs_by_level`/`targets_by_level`/zone records in place; returns the pair count."""

    reached = _terrain_reach(world.grids, gate_xy, start)
    cands = _candidates(catalog, world, reached)
    if not cands:
        return 0
    return _PortalRescue(catalog, world, reached, seed).run(cands)


def _is_coastal(grid: Sequence[Sequence[int]], ts: set[Tile], size: int) -> bool:
    W = H = size
    return any(
        0 <= x + dx < W and 0 <= y + dy < H and grid[y + dy][x + dx] == Terrain.WATER
        for (x, y) in ts
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
    )


def _candidates(
    catalog: Catalog, world: PortalWorld, reached: Container[tuple[int, int, int]]
) -> list[tuple[int, int, int, str]]:
    cands: list[tuple[int, int, int, str]] = []
    for lvl in sorted(world.zones_by_level):
        grid = world.grids[lvl]
        for zid, z in sorted(world.zones_by_level[lvl].items()):
            if z.terrain_type.is_barrier or z.area < PORTAL_MIN_AREA:
                continue
            terrain = catalog.terrain_name(z.terrain_type)
            ts = set(z.tiles_set)
            if any((x, y, lvl) in reached for (x, y) in ts):
                continue
            if lvl == 0 and _is_coastal(grid, ts, world.size):
                continue  # coastal: boat-reachable by design
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

        self.cover_by: dict[int, CoverIndex] = {
            lvl: CoverIndex(objs) for lvl, objs in world.objs_by_level.items()
        }

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
        self, lvl: int, appr: Tile, own_cells: Container[Tile], gident: Identity
    ) -> Tile | None:
        """First legal tile Chebyshev-1 from the near end's visitable cell (a monster's
        zone of control covers all 8 neighbours, so stepping INTO the portal forces the
        fight); None when the surroundings can't seat one."""
        grid = self.world.grids[lvl]
        st = self.state[lvl]
        W = H = self.world.size
        for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (-1, 1), (1, -1), (-1, -1)):
            g = (appr[0] + dx, appr[1] + dy)
            if (
                not (0 <= g[0] < W and 0 <= g[1] < H)
                or Terrain(grid[g[1]][g[0]]).is_barrier
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

    def run(self, cands: Sequence[tuple[int, int, int, str]]) -> int:
        n_placed = 0
        rescued: list[str] = []
        for _na, lvl, zid, terrain in cands:
            if n_placed >= MAX_PORTALS:
                print(
                    f"  portals: cap {MAX_PORTALS} reached, "
                    + f"{len(cands) - n_placed} unreachable zone(s) left decoration-filled"
                )
                break
            label = self._rescue(lvl, zid, terrain, n_placed)
            if label is None:
                continue
            n_placed += 1
            rescued.append(label)

        if n_placed:
            print(
                f"  special reward zones: {n_placed} rescued via guarded portals "
                + f"[{', '.join(rescued)}]"
            )
        return n_placed

    def _far_end(self, zone: _Enclave, ident: Identity) -> tuple[Tile, Fit] | None:
        st = self.state[zone.lvl]
        for t in sorted(zone.ts, key=partial(_centre_key, cx=zone.cx, cy=zone.cy)):
            fit = fits(ident, t, zone.ts, Clearance(st.occupied, st.near, st.reserved))
            if fit and self.cover_by[zone.lvl].accepts(_portal_end(zone.lvl, ident, t)):
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
            order = sorted(hts, key=partial(_centre_key, cx=zone.cx, cy=zone.cy))

        for t in order:
            fit = fits(ident, t, hts, Clearance(st.occupied, st.near, st.reserved))
            if fit is None or not self.cover_by[lvl].accepts(_portal_end(lvl, ident, t)):
                continue
            g = self._guard_spot(lvl, fit[2], set(fit[0]), gident)
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

    def _reward(self, zone: _Enclave, far_fit: Fit, far_appr: Tile) -> int:
        lvl = zone.lvl
        st = self.state[lvl]
        W = H = self.world.size
        # the reward upgrade: the portal makes the zone special
        zr = self.zr_by[lvl].get(zone.zid)
        if zr is None:  # zone skipped by the level pass (bare
            free = set(zone.ts) - st.occupied  # terrain): synth a minimal record
            zr = ZoneRecord(
                zid=zone.zid,
                terrain=zone.terrain,
                ts=frozenset(zone.ts),
                open_set=free,
                passable=free,
                reach=set(),
                used=set(),
            )
        zr.used.update(far_fit[0])  # the monolith's own cells
        robjs = place_reward_zone(
            self.catalog, RewardSite(zr, far_appr, (W, H), self.cover_by[lvl]), seed=self.seed
        )
        for o in robjs:
            o.level = lvl
        self.world.objs_by_level[lvl].extend(robjs)
        self.world.targets_by_level[lvl].extend((o.x, o.y) for o in robjs)
        st.occupied.update(
            (cx2, cy2) for o in robjs for cx2, cy2, _b in FP.anchored_cells(o.footprint, o.x, o.y)
        )
        return len(robjs)

    def _rescue(self, lvl: int, zid: int, terrain: str, n_placed: int) -> str | None:
        z = self.world.zones_by_level[lvl][zid]
        ts = set(z.tiles_set)
        st = self.state[lvl]
        ident = self.catalog.identity_of(PORTAL_ANIMS[n_placed % len(PORTAL_ANIMS)])
        cx, cy = z.centroid
        zone = _Enclave(lvl=lvl, zid=zid, terrain=terrain, ts=ts, cx=cx, cy=cy)

        far = self._far_end(zone, ident)
        if far is None:
            return None
        far_node, far_fit = far

        hosts = self._hosts(zone)

        gident = rnd_monster(self.catalog, min(7, 4 + len(ts) // 60))
        near = self._near_end(zone, ident, gident, hosts)
        if near is None:
            return None
        near_node, near_fit, gtile = near

        guard = PlacedObject.at(
            gident,
            gtile,
            level=lvl,
            purpose=Purpose.GUARD,
            options={"character": "hostile"},
        )
        far_appr = self._emit_end(lvl, ident, far_node, far_fit)
        _ = self._emit_end(lvl, ident, near_node, near_fit)
        if not self.cover_by[lvl].try_add(guard):
            return None
        self.world.objs_by_level[lvl].append(guard)
        st.occupied.add(gtile)

        n_robjs = self._reward(zone, far_fit, far_appr)
        return f"L{lvl}z{zid}({len(ts)}t,{n_robjs}obj)"

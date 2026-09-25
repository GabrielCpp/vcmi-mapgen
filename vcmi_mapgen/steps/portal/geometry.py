"""Portal rescue of unreachable zones and the target reachability check."""

import collections
import random
from collections.abc import Container, Mapping, Sequence
from dataclasses import dataclass
from functools import partial

from vcmi_mapgen import ontology as ON
from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.kit.terrain_lookup import TNAME
from vcmi_mapgen.models import CoverIndex, Identity, PlacedObject, Tile, Zone, ZoneRecord
from vcmi_mapgen.steps.gameplay.mines import mine_gameplay
from vcmi_mapgen.steps.gate.gates import GAP, Fit, fits, rnd_monster
from vcmi_mapgen.steps.pickup.scatter import place_one

MIN_AREA = 25  # matches GameplayStep's own zone floor


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
    walk: set[Tile] = set()
    hard: set[Tile] = set()
    for o in objs:
        soft = o.purpose in ("RESOURCE_PILE", "REWARD_PICKUP", "GUARD")
        for cx, cy, blk in OR.mask_cells(o.mask, o.x, o.y):
            if blk and not soft:
                (hard if o.purpose else walk).add((cx, cy))
    open_set = land - walk - hard
    targets_in = [t for t in targets if t in open_set]
    if not targets_in:
        return []
    root = targets_in[0]
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
    bad = [t for t in targets_in if t not in seen]
    if not bad:
        return []
    through_veg = land - hard
    reach = {root}
    queue = collections.deque([root])
    while queue:
        x, y = queue.popleft()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                n = (x + dx, y + dy)
                if n in through_veg and n not in reach:
                    reach.add(n)
                    queue.append(n)
    return [t for t in bad if t in reach]


def place_reward_zone(
    zr: ZoneRecord,
    entry: Tile,
    seed: int = 1,
    bounds: tuple[int, int] | None = None,
    cover: CoverIndex | None = None,
) -> list[PlacedObject]:
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
    terrain = zr.terrain
    st = mine_gameplay()[terrain]
    rng = random.Random(seed ^ (entry[0] * 92821) ^ (entry[1] * 131071) ^ 0x907A1)
    ts = zr.ts
    used = zr.used
    area = len(ts)

    # reach: what the portal's entry tile actually opens up (4-connected within passable)
    passable = zr.passable
    reach: set[Tile] = {entry} if entry in passable else set()
    q = [entry]
    while q:
        x, y = q.pop()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if n in passable and n not in reach:
                reach.add(n)
                q.append(n)
    if not reach:
        return []

    n_res = max(4, area // 10) + max(2, area // 25)
    pool_res = ON.pool("RESOURCE_PILE", terrain)
    objs: list[PlacedObject] = []
    val = 0

    spots = sorted(reach - used)
    rng.shuffle(spots)
    for t in spots:
        if n_res <= 0:
            break
        if place_one(
            objs,
            used,
            reach,
            rng,
            st,
            "RESOURCE_PILE",
            pool_res,
            t[0],
            t[1],
            cache=True,
            bounds=bounds,
            cover=cover,
        ):
            n_res -= 1
            val += 2

    if objs:
        # one interior guard near the zone's own centre: the portal guard gates entry, this
        # one gates the hoard itself — cache ladder (pp_pickup pocket convention) + 1
        cx = sum(x for x, _ in ts) / area
        cy = sum(y for _, y in ts) / area
        lvl = 1 + (val >= 4) + (val >= 7) + (val >= 10) + (val >= 13) + 1
        gident = rnd_monster(lvl)
        for t in sorted(reach - used, key=partial(_centre_key, cx=cx, cy=cy)):
            if place_one(
                objs,
                used,
                reach,
                rng,
                st,
                "GUARD",
                None,
                t[0],
                t[1],
                ident=gident,
                bounds=bounds,
                cover=cover,
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


def _guard_spot(
    appr: Tile,
    own_cells: Container[Tile],
    gident: Identity,
    grid: Sequence[Sequence[int]],
    st: _LevelState,
    W: int,
    H: int,
) -> Tile | None:
    """First legal tile Chebyshev-1 from the near end's visitable cell (a monster's
    zone of control covers all 8 neighbours, so stepping INTO the portal forces the
    fight); None when the surroundings can't seat one."""
    for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (-1, 1), (1, -1), (-1, -1)):
        g = (appr[0] + dx, appr[1] + dy)
        if (
            not (0 <= g[0] < W and 0 <= g[1] < H)
            or grid[g[1]][g[0]] >= 8
            or g in st.occupied
            or g in own_cells
            or g in st.reserved
        ):
            continue
        if all(
            0 <= gx < W
            and 0 <= gy < H
            and grid[gy][gx] < 8
            and (gx, gy) not in st.occupied
            and (gx, gy) not in own_cells
            for gx, gy in OR.mask_interactive_cells(gident.mask, g[0], g[1])
        ):
            return g
    return None


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
    if grids.get(lvl0) is not None and grids[lvl0][sy][sx] < 8:
        reached = {(sx, sy, lvl0)}
    q = collections.deque(reached)
    H = len(grids[lvl0])
    W = len(grids[lvl0][0])
    while q:
        x, y, lvl = q.popleft()
        if (x, y) in gate_xy:
            for l2, g2 in grids.items():
                if l2 != lvl and g2[y][x] < 8 and (x, y, l2) not in reached:
                    reached.add((x, y, l2))
                    q.append((x, y, l2))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if (
                0 <= nx < W
                and 0 <= ny < H
                and grids[lvl][ny][nx] < 8
                and (nx, ny, lvl) not in reached
            ):
                reached.add((nx, ny, lvl))
                q.append((nx, ny, lvl))
    return reached


def rescue_unreachable_zones(
    size: int,
    grids: Mapping[int, Sequence[Sequence[int]]],
    zones_by_level: Mapping[int, Mapping[int, Zone]],
    objs_by_level: Mapping[int, list[PlacedObject]],
    targets_by_level: Mapping[int, list[Tile]],
    zone_records_by_level: Mapping[int, Sequence[ZoneRecord]],
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

    reached = _terrain_reach(grids, gate_xy, start)
    W = H = size

    cands: list[tuple[int, int, int, str]] = []
    for lvl in sorted(zones_by_level):
        grid = grids[lvl]
        for zid, z in sorted(zones_by_level[lvl].items()):
            terrain = TNAME.get(z.terrain_type)
            if terrain is None or terrain in ("water", "rock") or z.area < PORTAL_MIN_AREA:
                continue
            ts = set(z.tiles_set)
            if any((x, y, lvl) in reached for (x, y) in ts):
                continue
            if lvl == 0 and any(
                0 <= x + dx < W and 0 <= y + dy < H and grid[y + dy][x + dx] == 8
                for (x, y) in ts
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            ):
                continue  # coastal: boat-reachable by design
            cands.append((-z.area, lvl, zid, terrain))
    cands.sort()
    if not cands:
        return 0

    # per-level placement state, built once from everything already on the map: gameplay
    # footprints (whole cells, GAP-inflated exactly like place_zone/place_gates) plus
    # vegetation blocking cells (a teleporter must not sit buried in a tree), plus the
    # level's named targets as reserved doorways.
    state: dict[int, _LevelState] = {}
    for lvl, objs in objs_by_level.items():
        game_cells: set[Tile] = set()
        veg_blk: set[Tile] = set()
        for o in objs:
            cells = list(OR.mask_cells(o.mask, o.x, o.y))
            if not o.purpose:
                veg_blk.update((cx, cy) for cx, cy, b in cells if b)
            else:
                game_cells.update((cx, cy) for cx, cy, _b in cells)
        near = set(veg_blk)
        for cx, cy in game_cells:
            for gx in range(-GAP, GAP + 1):
                for gy in range(-GAP, GAP + 1):
                    near.add((cx + gx, cy + gy))
        state[lvl] = _LevelState(
            occupied=game_cells | veg_blk,
            near=near,
            reserved=set(targets_by_level[lvl]),
        )

    zr_by = {
        lvl: {zr.zid: zr for zr in (zone_records_by_level.get(lvl) or ())} for lvl in zones_by_level
    }
    towns = {
        lvl: [(o.x, o.y) for o in objs if o.purpose == "TOWN"]
        for lvl, objs in objs_by_level.items()
    }

    cover_by = {lvl: CoverIndex(objs) for lvl, objs in objs_by_level.items()}

    def portal_end(lvl: int, ident: Identity, node: Tile) -> PlacedObject:
        return PlacedObject.at(ident, node[0], node[1], level=lvl, purpose="TRANSPORT")

    def emit_end(lvl: int, ident: Identity, node: Tile, fit: Fit) -> Tile:
        allc, _blk, approach = fit
        end = portal_end(lvl, ident, node)
        cover_by[lvl].add(end)
        objs_by_level[lvl].append(end)
        st = state[lvl]
        st.occupied.update(allc)
        for cx, cy in allc:
            for gx in range(-GAP, GAP + 1):
                for gy in range(-GAP, GAP + 1):
                    st.near.add((cx + gx, cy + gy))
        st.reserved.add(approach)
        targets_by_level[lvl].append(approach)
        return approach

    n_placed = 0
    rescued: list[str] = []
    for _na, lvl, zid, terrain in cands:
        if n_placed >= MAX_PORTALS:
            print(
                f"  portals: cap {MAX_PORTALS} reached, "
                + f"{len(cands) - n_placed} unreachable zone(s) left decoration-filled"
            )
            break
        z = zones_by_level[lvl][zid]
        ts = set(z.tiles_set)
        st = state[lvl]
        ident = ON.identity_of(PORTAL_ANIMS[n_placed % len(PORTAL_ANIMS)])
        cx, cy = z.centroid

        far_fit: Fit | None = None
        far_node: Tile | None = None
        for t in sorted(ts, key=partial(_centre_key, cx=cx, cy=cy)):
            fit = fits(ident, t[0], t[1], ts, st.occupied, st.near, st.reserved)
            if fit and cover_by[lvl].accepts(portal_end(lvl, ident, t)):
                far_fit, far_node = fit, t
                break
        if far_fit is None or far_node is None:
            continue

        hosts: list[tuple[float, int, int]] = []
        for hzid, hz in sorted(zones_by_level[lvl].items()):
            if hzid == zid or TNAME.get(hz.terrain_type) in (None, "water", "rock"):
                continue
            if hz.area < MIN_AREA:
                continue
            if not any((x, y, lvl) in reached for (x, y) in hz.tiles_set):
                continue
            hx, hy = hz.centroid
            hosts.append(((hx - cx) ** 2 + (hy - cy) ** 2, -hz.area, hzid))
        hosts.sort()

        gident = rnd_monster(min(7, 4 + len(ts) // 60))
        near_fit: Fit | None = None
        near_node: Tile | None = None
        gtile: Tile | None = None
        for _d, _ha, hzid in hosts[:3]:
            hts = set(zones_by_level[lvl][hzid].tiles_set)
            tl = towns[lvl]
            if tl:  # outskirts: value sits outward
                order = sorted(hts, key=partial(_outskirts_key, towns=tl))
            else:
                order = sorted(hts, key=partial(_centre_key, cx=cx, cy=cy))

            for t in order:
                fit = fits(ident, t[0], t[1], hts, st.occupied, st.near, st.reserved)
                if fit is None or not cover_by[lvl].accepts(portal_end(lvl, ident, t)):
                    continue
                g = _guard_spot(fit[2], set(fit[0]), gident, grids[lvl], st, W, H)
                if g is None:  # a portal must be guardable — skip
                    continue  # candidates with no room for the guard
                near_fit, near_node, gtile = fit, t, g
                break
            if near_fit:
                break
        if near_fit is None or near_node is None or gtile is None:
            continue

        guard = PlacedObject.at(
            gident,
            gtile[0],
            gtile[1],
            level=lvl,
            purpose="GUARD",
            options={"character": "hostile"},
        )
        far_appr = emit_end(lvl, ident, far_node, far_fit)
        _ = emit_end(lvl, ident, near_node, near_fit)
        if not cover_by[lvl].try_add(guard):
            continue
        objs_by_level[lvl].append(guard)
        st.occupied.add(gtile)

        # the reward upgrade: the portal makes the zone special
        zr = zr_by[lvl].get(zid)
        if zr is None:  # zone skipped by the level pass (bare
            free = set(ts) - st.occupied  # terrain): synth a minimal record
            zr = ZoneRecord(
                zid=zid,
                terrain=terrain,
                ts=frozenset(ts),
                open_set=free,
                passable=free,
                reach=set(),
                used=set(),
            )
        zr.used.update(far_fit[0])  # the monolith's own cells
        robjs = place_reward_zone(zr, far_appr, seed=seed, bounds=(W, H), cover=cover_by[lvl])
        for o in robjs:
            o.level = lvl
        objs_by_level[lvl].extend(robjs)
        targets_by_level[lvl].extend((o.x, o.y) for o in robjs)
        st.occupied.update(
            (cx2, cy2) for o in robjs for cx2, cy2, _b in OR.mask_cells(o.mask, o.x, o.y)
        )

        n_placed += 1
        rescued.append(f"L{lvl}z{zid}({len(ts)}t,{len(robjs)}obj)")

    if n_placed:
        print(
            f"  special reward zones: {n_placed} rescued via guarded portals [{', '.join(rescued)}]"
        )
    return n_placed

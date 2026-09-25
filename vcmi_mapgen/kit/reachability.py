"""Global traversability gate (tile-level).

The abstract `deps_embed.connectivity` proves the zone GRAPH is connected through
gates; `deps_realize.reachability_repair` only guarantees each object has *some*
walkable approach. Neither proves a hero can actually WALK from the starting town
to every zone, town and mine on the realized grid -- a chokepoint can be carved
but walled off by mountains beyond it, or a reward pocket can be sealed by water.

This module BFS-walks passable land (through carved chokepoints) from the start
town and asserts every zone, every town and every mine is reachable. Wired into
`ralph/verify.sh`, an unreachable map FAILS the gate.
"""

import collections
from collections.abc import Mapping
from dataclasses import dataclass

from vcmi_mapgen.kit import objects as OBJ
from vcmi_mapgen.models import PlacedObject, Tile

type Grid = tuple[list[list[bool]], int, int]
type LevelTile = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class ZoneMap:
    zone: list[list[int]]
    n_zones: int


@dataclass(frozen=True, slots=True)
class ReachabilityReport:
    ok: bool
    start: Tile | None
    levels: int
    reached_tiles: int
    passable_tiles: int
    cavern_reached_tiles: int | None
    zones_reached: int | None
    zones_total: int | None
    bad_zones: list[int]
    unreachable_towns: list[LevelTile]
    unreachable_mines: list[LevelTile]


WATER = 8
ROCK = 9
NB4 = [(1, 0), (-1, 0), (0, 1), (0, -1)]
NB8 = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]


def passable_grid(fm: OBJ.FaithfulMap, level: int = 0) -> Grid:
    """A tile on level `level` is blocked when it is water/rock or covered by a blocking mask cell
    ('B' or 'X') of an object ON THAT LEVEL. Passable visitable 'A' cells (the tile a hero stands
    on) stay passable; 'X' (a building action tile) blocks and is visited from an adjacent tile.
    Rock (9) walls the underground."""
    terr = fm.terrain[level]
    W, H = len(terr[0]), len(terr)
    blocked = [[terr[y][x].t in (WATER, ROCK) for x in range(W)] for y in range(H)]
    for o in fm.objects:
        if o.level != level:
            continue
        for cx, cy, blk in OBJ.mask_cells(o.mask, o.x, o.y):
            if 0 <= cx < W and 0 <= cy < H and blk:
                blocked[cy][cx] = True
    return blocked, W, H


def _a_cells(o: PlacedObject) -> list[Tile]:
    # visitable anchors: 'A' (stand on) and 'X' (blocked building tile, visited from adjacent — its
    # own tile is blocked so `_approaches` will yield its passable neighbours, not the tile itself).
    return OBJ.mask_interactive_cells(o.mask, o.x, o.y)


def _approaches(o: PlacedObject, blocked: list[list[bool]], W: int, H: int) -> set[Tile]:
    """Passable tiles from which object o can be entered (4-adjacent to an 'A'
    cell, plus the 'A' cell itself if it is walkable -- monsters block nothing)."""
    res: set[Tile] = set()
    for ax, ay in _a_cells(o):
        if 0 <= ax < W and 0 <= ay < H and not blocked[ay][ax]:
            res.add((ax, ay))
        for dx, dy in NB4:
            nx, ny = ax + dx, ay + dy
            if 0 <= nx < W and 0 <= ny < H and not blocked[ny][nx]:
                res.add((nx, ny))
    return res


def _start_seed(
    fm: OBJ.FaithfulMap, blocked: list[list[bool]], W: int, H: int
) -> tuple[set[Tile], PlacedObject | None]:
    """Passable tiles next to the player's starting town. main_town is stored at
    (anchor-2, anchor-2); the town object's anchor is therefore main_town+(2,2)."""
    mt = fm.main_town
    towns = [o for o in fm.objects if OBJ.type_to_purpose(o.type) == "TOWN"]
    start: PlacedObject | None = None
    if mt is not None:
        ax, ay = mt[0] + 2, mt[1] + 2
        start = min(towns, key=lambda o: (o.x - ax) ** 2 + (o.y - ay) ** 2, default=None)
    if start is None and towns:  # fallback: town nearest map centre
        start = min(towns, key=lambda o: (o.x - W // 2) ** 2 + (o.y - H // 2) ** 2)
    if start is None:
        return set(), None
    return _approaches(start, blocked, W, H), start


def _gate_groups(
    fm: OBJ.FaithfulMap,
) -> collections.defaultdict[tuple[str, int | str | None, int], list[PlacedObject]]:
    by_key: collections.defaultdict[tuple[str, int | str | None, int], list[PlacedObject]] = (
        collections.defaultdict(list)
    )
    for o in fm.objects:
        if o.type == "subterraneanGate":
            by_key[("sg", o.x, o.y)].append(o)
        elif o.type == "monolithTwoWay":
            by_key[("m2", o.subtype, 0)].append(o)
    return by_key


def _end_approaches(ends: list[PlacedObject], grids: Mapping[int, Grid]) -> list[set[LevelTile]]:
    appr: list[set[LevelTile]] = []
    for o in ends:
        level = o.level
        if level not in grids:
            continue
        blocked, W, H = grids[level]
        appr.append({(x, y, level) for x, y in _approaches(o, blocked, W, H)})
    return appr


def _gate_links(
    fm: OBJ.FaithfulMap, grids: Mapping[int, Grid]
) -> collections.defaultdict[LevelTile, set[LevelTile]]:
    """Teleport networks. Subterranean gates come in pairs sharing (x, y) across levels;
    two-way monoliths network ALL ends of the same subtype (H3 semantics — used by
    steps.portal.geometry to rescue otherwise-unreachable zones as guarded reward zones).
    Stepping onto any end
    teleports the hero to the others. Returns trigger map: reaching any (x,y,l) approach
    tile of an end enqueues every partner end's approach tiles (x,y,l')."""
    by_key = _gate_groups(fm)
    trigger: collections.defaultdict[LevelTile, set[LevelTile]] = collections.defaultdict(set)
    for ends in by_key.values():
        appr = _end_approaches(ends, grids)
        for i in range(len(appr)):
            for j in range(len(appr)):
                if i != j:
                    for t in appr[i]:
                        trigger[t] |= appr[j]
    return trigger


def _walk(
    seed: set[Tile],
    trigger: Mapping[LevelTile, set[LevelTile]],
    grids: Mapping[int, Grid],
) -> set[LevelTile]:
    reached: set[LevelTile] = {(x, y, 0) for x, y in seed}
    q = collections.deque(reached)
    while q:
        x, y, level = q.popleft()
        for s in trigger.get((x, y, level), ()):  # gate teleport across levels
            if s not in reached:
                reached.add(s)
                q.append(s)
        bl, lw, lh = grids[level]
        for dx, dy in NB4:
            nx, ny = x + dx, y + dy
            if 0 <= nx < lw and 0 <= ny < lh and not bl[ny][nx] and (nx, ny, level) not in reached:
                reached.add((nx, ny, level))
                q.append((nx, ny, level))
    return reached


def _obj_reachable(o: PlacedObject, reached: set[LevelTile]) -> bool:
    level = o.level
    for ax, ay in _a_cells(o):
        if (ax, ay, level) in reached:
            return True
        for dx, dy in NB4:
            if (ax + dx, ay + dy, level) in reached:
                return True
    return False


def _unreachable_towns_and_mines(
    fm: OBJ.FaithfulMap, reached: set[LevelTile]
) -> tuple[list[LevelTile], list[LevelTile]]:
    bad_towns: list[LevelTile] = []
    bad_mines: list[LevelTile] = []
    for o in fm.objects:
        pp = OBJ.type_to_purpose(o.type)
        if pp == "TOWN" and not _obj_reachable(o, reached):
            bad_towns.append((o.x, o.y, o.level))
        elif pp == "MINE" and not _obj_reachable(o, reached):
            bad_mines.append((o.x, o.y, o.level))
    return bad_towns, bad_mines


def _zone_coverage(
    em: ZoneMap | None, reached: set[LevelTile]
) -> tuple[int | None, int | None, list[int]]:
    zones_reached: int | None = None
    zones_total: int | None = None
    bad_zones: list[int] = []
    if em is not None:
        zone = em.zone
        total = em.n_zones
        seen_z = {zone[y][x] for (x, y, level) in reached if level == 0}
        zones_reached, zones_total = len(seen_z), total
        bad_zones = sorted(set(range(total)) - seen_z)
    return zones_reached, zones_total, bad_zones


def traverse(fm: OBJ.FaithfulMap, em: ZoneMap | None = None) -> ReachabilityReport:
    """Return a reachability report for the realized (possibly two-level) map.
    BFS walks passable land from the start town, descending/ascending through
    subterranean-gate pairs, so cavern objects are reachable only if the surface
    gate is reachable and the cavern is connected to it."""
    grids = {level: passable_grid(fm, level) for level in range(len(fm.terrain))}
    blocked, W, H = grids[0]
    seed, start = _start_seed(fm, blocked, W, H)
    trigger = _gate_links(fm, grids)

    reached = _walk(seed, trigger, grids)
    bad_towns, bad_mines = _unreachable_towns_and_mines(fm, reached)
    zones_reached, zones_total, bad_zones = _zone_coverage(em, reached)

    n_passable = sum(not blocked[y][x] for y in range(H) for x in range(W))
    cavern_reached = sum(1 for (_x, _y, level) in reached if level == 1) if len(grids) > 1 else None
    ok = start is not None and not bad_towns and not bad_mines and not bad_zones
    return ReachabilityReport(
        ok=ok,
        start=(start.x, start.y) if start else None,
        levels=len(grids),
        reached_tiles=len(reached),
        passable_tiles=n_passable,
        cavern_reached_tiles=cavern_reached,
        zones_reached=zones_reached,
        zones_total=zones_total,
        bad_zones=bad_zones,
        unreachable_towns=bad_towns,
        unreachable_mines=bad_mines,
    )


# traverse() is imported as a library by research/mapeval.py (map-quality scoring).
# The former __main__ self-test depended on the removed deps_realize experiment.

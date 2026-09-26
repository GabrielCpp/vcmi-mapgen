"""Shared tile-classification helpers for overlays operating on a MapState:
passable-tile computation, background/structure/solo-visit object classification,
a tile -> zone lookup, and loot-zone tile detection -- reused by PocketOverlay,
PassageOverlay, GuardOverlay so each doesn't reimplement blocked-tile computation.
"""

from __future__ import annotations

import collections
from collections.abc import Iterable, Mapping, Sequence

from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.models import Cell, PlacedObject, Tile, Zone

_WATER, _ROCK = 8, 9
NB8: list[Tile] = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]

# A visitable object whose visit tile is "owned" by the structure for pocket geometry
# (excluded from passable-for-pockets even though it's walkable terrain).
STRUCTURE_PURPOSES = frozenset(
    {
        "TOWN",
        "MINE",
        "DWELLING",
        "STAT_PERMANENT",
        "BONUS_TEMP",
        "SPELL_SKILL",
        "BANK",
        "INFO",
        "MANA",
        "QUEST_GATE",
    }
)

_PREFIX_TO_CODE: dict[str, int] = {
    "dt": 0,
    "sa": 1,
    "gr": 2,
    "sn": 3,
    "sw": 4,
    "rg": 5,
    "sb": 6,
    "lv": 7,
    "wt": 8,
    "ro": 9,
    "hl": 10,
    "wa": 11,
}


def terrain_code(cell: str | Cell) -> int:
    """Extract the integer terrain code from a tile string or a tile cell."""
    if isinstance(cell, Cell):
        return cell.t
    if len(cell) >= 2:
        return _PREFIX_TO_CODE.get(cell[:2], 0)
    return 0


def passable_tiles(
    surf: Sequence[Sequence[str | Cell]], objs: Iterable[PlacedObject], level: int
) -> set[Tile]:
    """Land tiles (not water/rock) minus any object's blocking footprint on `level`."""
    H, W = len(surf), len(surf[0])
    land = {
        (x, y)
        for y in range(H)
        for x in range(W)
        if terrain_code(surf[y][x]) not in (_WATER, _ROCK)
    }
    blocked: set[Tile] = set()
    for o in objs:
        if o.level != level:
            continue
        mask = o.mask
        if not mask:
            continue
        for tx, ty, blk in OR.mask_cells(mask, o.x, o.y):
            if blk:
                blocked.add((tx, ty))
    return land - blocked


def classify_objects(
    objs: Iterable[PlacedObject], level: int
) -> tuple[set[Tile], set[Tile], set[Tile], set[Tile]]:
    """(background, struct_body, struct_visit, solo_visit) tile sets for `level`.

    solo_visit: structures with NO blocking body cells and exactly ONE visit tile --
    pure single-tile visitable objects (shrines, events, signs). They may sit inside
    a pocket but are never pocket entrance/wall tiles.
    """
    background: set[Tile] = set()
    struct_body: set[Tile] = set()
    struct_visit: set[Tile] = set()
    solo_visit: set[Tile] = set()
    for o in objs:
        if o.level != level:
            continue
        purpose = o.purpose
        mask = o.mask
        if not mask:
            continue
        ox, oy = o.x, o.y
        if purpose in STRUCTURE_PURPOSES or purpose == "WATER_TRANSPORT":
            visit = set(OR.mask_interactive_cells(mask, ox, oy))
            body = {
                (cx, cy)
                for cx, cy, blk in OR.mask_cells(mask, ox, oy)
                if blk and (cx, cy) not in visit
            }
            if purpose != "WATER_TRANSPORT" and not body and len(visit) == 1:
                solo_visit |= visit
            else:
                struct_visit |= visit
                struct_body |= body
        elif not purpose or purpose == "DECORATION":
            for cx, cy, blk in OR.mask_cells(mask, ox, oy):
                if blk:
                    background.add((cx, cy))
    background -= struct_body | struct_visit | solo_visit
    return background, struct_body, struct_visit, solo_visit


def zone_lookup(zones: Mapping[int, Zone]) -> dict[Tile, int]:
    """tile -> zone id, from a SegmentStep-populated `state.zones[level]` dict."""
    lookup: dict[Tile, int] = {}
    for zid, z in zones.items():
        for t in z.tiles_set:
            lookup[t] = zid
    return lookup


def passage_tiles(lookup: Mapping[Tile, int], passable: set[Tile]) -> set[Tile]:
    """Passable tiles that border a passable tile in a DIFFERENT zone -- the
    walkable seam between two zones."""
    passages: set[Tile] = set()
    for x, y in passable:
        zid = lookup.get((x, y), -1)
        if zid < 0:
            continue
        for dx, dy in NB8:
            nb = (x + dx, y + dy)
            if nb in passable and lookup.get(nb, -1) != zid:
                passages.add((x, y))
                break
    return passages


def loot_zone_tiles(
    zones: Mapping[int, Zone], objs: Iterable[PlacedObject], level: int, max_tiles: int = 80
) -> set[Tile]:
    """Tiles belonging to a 'loot zone' (small, town-free, single-boundary-cluster
    zone reached via a gate/monolith access pair) -- the same detection
    steps.gated.placer uses, so pocket detection doesn't double-count them."""
    town_tiles = _town_tiles(objs, level)

    all_ts: set[Tile] = set()
    for z in zones.values():
        all_ts |= set(z.tiles_set)

    loot: set[Tile] = set()
    for z in zones.values():
        ts = set(z.tiles_set)
        if len(ts) > max_tiles or any(t in town_tiles for t in ts):
            continue
        ext_ts = all_ts - ts
        boundary = {t for t in ts if any((t[0] + dx, t[1] + dy) in ext_ts for dx, dy in NB8)}
        if _boundary_clusters(boundary) == 1:
            loot |= ts
    return loot


def _town_tiles(objs: Iterable[PlacedObject], level: int) -> set[Tile]:
    town_tiles: set[Tile] = set()
    for o in objs:
        if o.level == level and o.purpose == "TOWN":
            mask = o.mask
            if mask:
                for cx, cy, _ in OR.mask_cells(mask, o.x, o.y):
                    town_tiles.add((cx, cy))
    return town_tiles


def _boundary_clusters(boundary: set[Tile]) -> int:
    seen: set[Tile] = set()
    n_clusters = 0
    for s in sorted(boundary):
        if s in seen:
            continue
        n_clusters += 1
        if n_clusters > 1:
            break
        q = collections.deque[Tile]([s])
        seen.add(s)
        while q:
            cx, cy = q.popleft()
            for dx, dy in NB8:
                nb = (cx + dx, cy + dy)
                if nb in boundary and nb not in seen:
                    seen.add(nb)
                    q.append(nb)
    return n_clusters

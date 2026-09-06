"""Shared tile-classification helpers for overlays operating on a MapState:
passable-tile computation, background/structure/solo-visit object classification,
a tile -> zone lookup, and loot-zone tile detection -- reused by PocketOverlay,
PassageOverlay, GuardOverlay so each doesn't reimplement blocked-tile computation.
"""
from __future__ import annotations

import collections

from vcmi_mapgen.kit import objects as OR

_WATER, _ROCK = 8, 9
NB8 = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]

# A visitable object whose visit tile is "owned" by the structure for pocket geometry
# (excluded from passable-for-pockets even though it's walkable terrain).
STRUCTURE_PURPOSES = frozenset({
    "TOWN", "MINE", "DWELLING",
    "STAT_PERMANENT", "BONUS_TEMP", "SPELL_SKILL",
    "BANK", "INFO", "MANA", "QUEST_GATE",
})

_PREFIX_TO_CODE = {
    "dt": 0, "sa": 1, "gr": 2, "sn": 3, "sw": 4,
    "rg": 5, "sb": 6, "lv": 7, "wt": 8, "ro": 9, "hl": 10, "wa": 11,
}


def _terrain_code(cell) -> int:
    if isinstance(cell, dict):
        return int(cell.get("t", 0))
    if isinstance(cell, str) and len(cell) >= 2:
        return _PREFIX_TO_CODE.get(cell[:2], 0)
    return 0


def _obj_mask(o):
    return o.get("mask") or (o.get("template") or {}).get("mask")


def passable_tiles(surf, objs, level: int) -> set:
    """Land tiles (not water/rock) minus any object's blocking footprint on `level`."""
    H, W = len(surf), len(surf[0])
    land = {(x, y) for y in range(H) for x in range(W)
            if _terrain_code(surf[y][x]) not in (_WATER, _ROCK)}
    blocked = set()
    for o in objs:
        if o.get("l", 0) != level:
            continue
        mask = _obj_mask(o)
        if not mask:
            continue
        for tx, ty, blk in OR.mask_cells(mask, o.get("x", 0), o.get("y", 0)):
            if blk:
                blocked.add((tx, ty))
    return land - blocked


def classify_objects(objs, level: int):
    """(background, struct_body, struct_visit, solo_visit) tile sets for `level`.

    solo_visit: structures with NO blocking body cells and exactly ONE visit tile --
    pure single-tile visitable objects (shrines, events, signs). They may sit inside
    a pocket but are never pocket entrance/wall tiles.
    """
    background, struct_body, struct_visit, solo_visit = set(), set(), set(), set()
    for o in objs:
        if o.get("l", 0) != level:
            continue
        purpose = o.get("purpose") or ""
        mask = _obj_mask(o)
        if not mask:
            continue
        ox, oy = o.get("x", 0), o.get("y", 0)
        if purpose in STRUCTURE_PURPOSES or purpose == "WATER_TRANSPORT":
            visit = set(OR.mask_interactive_cells(mask, ox, oy))
            body = {(cx, cy) for cx, cy, blk in OR.mask_cells(mask, ox, oy)
                    if blk and (cx, cy) not in visit}
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


def zone_lookup(zones: dict) -> dict:
    """tile -> zone id, from a SegmentStep-populated `state.zones[level]` dict."""
    lookup = {}
    for zid, z in zones.items():
        for t in z.get("tiles_set", ()):
            lookup[t] = zid
    return lookup


def passage_tiles(lookup: dict, passable: set) -> set:
    """Passable tiles that border a passable tile in a DIFFERENT zone -- the
    walkable seam between two zones."""
    passages = set()
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


def loot_zone_tiles(zones: dict, objs, level: int, max_tiles: int = 80) -> set:
    """Tiles belonging to a 'loot zone' (small, town-free, single-boundary-cluster
    zone reached via a gate/monolith access pair) -- the same detection
    steps.pickup.loot_zones uses, so pocket detection doesn't double-count them."""
    town_tiles = set()
    for o in objs:
        if o.get("l", 0) == level and o.get("purpose") == "TOWN":
            mask = _obj_mask(o)
            if mask:
                for cx, cy, _ in OR.mask_cells(mask, o.get("x", 0), o.get("y", 0)):
                    town_tiles.add((cx, cy))

    all_ts = set()
    for z in zones.values():
        all_ts |= set(z.get("tiles_set", ()))

    loot = set()
    for z in zones.values():
        ts = set(z.get("tiles_set", ()))
        if len(ts) > max_tiles or any(t in town_tiles for t in ts):
            continue
        ext_ts = all_ts - ts
        boundary = {t for t in ts if any((t[0] + dx, t[1] + dy) in ext_ts for dx, dy in NB8)}
        seen, n_clusters = set(), 0
        for s in sorted(boundary):
            if s in seen:
                continue
            n_clusters += 1
            if n_clusters > 1:
                break
            q = collections.deque([s])
            seen.add(s)
            while q:
                cx, cy = q.popleft()
                for dx, dy in NB8:
                    nb = (cx + dx, cy + dy)
                    if nb in boundary and nb not in seen:
                        seen.add(nb)
                        q.append(nb)
        if n_clusters == 1:
            loot |= ts
    return loot

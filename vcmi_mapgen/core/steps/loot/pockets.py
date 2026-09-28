"""Pocket geometry for the guarded caches: the deduped nooks, the tiles a hero reaches
diagonally, and the town-to-mine routes a new pocket guard must not cut."""

import collections
from collections.abc import Collection, Container, Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from itertools import pairwise

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.geometry import NB8
from vcmi_mapgen.core.grid.pockets import mouth_key
from vcmi_mapgen.core.model import Footprint, PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.planning.zone_index import ZoneRecord


def guard_stand(mask: Footprint, x: int, y: int) -> set[Tile]:
    return set(FP.interactive_cells(mask, x, y))


def _approach_tiles(mask: Footprint, x: int, y: int, passable: Container[Tile]) -> set[Tile]:
    """Passable tiles a hero could stand on to visit this object -- its own interactive
    cell(s) when walk-on, plus every passable 8-neighbour of them (covers a
    blocked-entrance 'X' interactive cell, which is clicked from an adjacent tile, never
    stood on itself)."""
    ap: set[Tile] = set()
    for ix, iy in FP.interactive_cells(mask, x, y):
        if (ix, iy) in passable:
            ap.add((ix, iy))
        for dx, dy in NB8:
            nb = (ix + dx, iy + dy)
            if nb in passable:
                ap.add(nb)
    return ap


def reachable(
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
    catalog: Catalog,
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
        pairs.extend(_home_zone_pairs(catalog, existing_objs, ts, global_true))
    return pairs, base_blocked


def _mine_cells(existing_objs: Sequence[PlacedObject]) -> set[Tile]:
    mine_cells: set[Tile] = set()
    for o in existing_objs:
        if o.purpose == Purpose.MINE:
            mask = o.footprint
            if mask.cells:
                mine_cells |= {(cx, cy) for cx, cy, _b in FP.anchored_cells(mask, o.x, o.y)}
    return mine_cells


def _is_mine_guard(o: PlacedObject, mine_cells: Iterable[Tile]) -> bool:
    return any(max(abs(o.x - mx), abs(o.y - my)) <= 1 for mx, my in mine_cells)


def _base_blocked(existing_objs: Sequence[PlacedObject], mine_cells: set[Tile]) -> set[Tile]:
    base_blocked: set[Tile] = set()
    for o in existing_objs:
        if o.purpose == Purpose.GUARD and not _is_mine_guard(o, mine_cells):
            mask = o.footprint
            if mask.cells:
                base_blocked |= guard_stand(mask, o.x, o.y)
    return base_blocked


def _home_zone_pairs(
    catalog: Catalog,
    existing_objs: Sequence[PlacedObject],
    ts: AbstractSet[Tile],
    global_true: Container[Tile],
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
            o.purpose == Purpose.MINE
            and catalog.identity_of(o.kind).subtype in ("sawmill", "orePit")
            and (o.x, o.y) in ts
        ):
            continue
        mine_ap = _approach_tiles(o.footprint, o.x, o.y, global_true)
        if mine_ap:
            pairs.append((frozenset(town_ap), frozenset(mine_ap)))
    return pairs


def reach8(open_set: Container[Tile], seed: Iterable[Tile]) -> set[Tile]:
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


def guard_stands(g: Tile, pocket: frozenset[Tile], mouth: frozenset[Tile]) -> list[Tile]:
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

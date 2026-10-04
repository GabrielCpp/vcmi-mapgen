"""Pocket (sealable-nook) detection and each pocket tile's depth from its mouth."""

import collections
from collections.abc import Collection, Container, Mapping, Sequence
from collections.abc import Set as AbstractSet
from itertools import pairwise

from vcmi_mapgen.core.grid.geometry import NB8
from vcmi_mapgen.core.grid.reach import distances
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.priors.pocket_masks import PocketMask

POCKET_NOOK_BLOCKED = 4  # mouth_key's "in a neck" tiebreak: a mouth tile counts as
# IN the neck when >=4 of its 8 neighbours are blocking

ROOM_CAP = 16

type Pockets = dict[int, dict[Tile, float]]


def mouth_key(
    reach: Container[Tile], mouth: Tile, pocket: Collection[Tile]
) -> tuple[int, int, int, int, Tile]:
    """Sort key ranking candidate mouths for the SAME physical nook, best (smallest)
    first. Preference order, derived from the user's drawings (the monster `O` sits at
    the pocket's natural opening):
      1. a mouth that is itself IN a neck (>=4 blocked neighbours — a corridor entrance)
         beats one standing a tile out in the open field, even when the open-field guard
         technically seals one extra tile via its ZoC;
      2. larger pocket (outermost mouth of a nested dead-end corridor);
      3. orthogonally adjacent to the pocket (guard facing the nook, not on a diagonal);
      4. more pocket tiles adjacent (better coverage), then plain tile order."""
    blocked = sum(1 for dx, dy in NB8 if (mouth[0] + dx, mouth[1] + dy) not in reach)
    orth = any(abs(mouth[0] - t[0]) + abs(mouth[1] - t[1]) == 1 for t in pocket)
    adj8 = sum(1 for t in pocket if max(abs(mouth[0] - t[0]), abs(mouth[1] - t[1])) == 1)
    return (
        0 if blocked >= POCKET_NOOK_BLOCKED else 1,
        -len(pocket),
        0 if orth else 1,
        -adj8,
        mouth,
    )


def find_pockets(
    reach: Collection[Tile],
    masks: Sequence[PocketMask],
    access: Container[Tile],
    occupied: Container[Tile],
) -> dict[Tile, tuple[frozenset[Tile], frozenset[Tile]]]:
    found: dict[Tile, tuple[frozenset[Tile], frozenset[Tile]]] = {}
    for g in sorted(reach):
        if g in access or g in occupied:
            continue
        blocked = sum(1 for dx, dy in NB8 if (g[0] + dx, g[1] + dy) not in reach)
        if blocked == 0:
            continue
        for mask in masks:
            if mask.walls_by_guard > blocked or not _matches(reach, access, g, mask):
                continue
            pocket = frozenset((g[0] + dx, g[1] + dy) for dx, dy in mask.free)
            if not _has_exit(reach, g, pocket):
                continue
            if g not in found or len(pocket) > len(found[g][0]):
                found[g] = (pocket, frozenset({g}))
    return found


def find_rooms(
    reach: AbstractSet[Tile], barred: Container[Tile], cap: int = ROOM_CAP
) -> dict[Tile, tuple[frozenset[Tile], frozenset[Tile]]]:
    found: dict[Tile, tuple[frozenset[Tile], frozenset[Tile]]] = {}
    for g in sorted(reach):
        if g in barred:
            continue
        ring = [(g[0] + dx, g[1] + dy) for dx, dy in NB8 if (g[0] + dx, g[1] + dy) in reach]
        parts = _ring_parts(ring)
        if len(parts) < 2:
            continue
        for start in parts:
            room = _bounded_region(reach, g, start, cap)
            if room is None or all(t in room for t in ring) or any(t in barred for t in room):
                continue
            if g not in found or len(room) > len(found[g][0]):
                found[g] = (room, frozenset({g}))
    return found


def _ring_parts(ring: Sequence[Tile]) -> list[Tile]:
    parent = {t: t for t in ring}

    def find(t: Tile) -> Tile:
        while parent[t] != t:
            t = parent[t]
        return t

    for a in ring:
        for b in ring:
            if max(abs(a[0] - b[0]), abs(a[1] - b[1])) == 1:
                parent[find(a)] = find(b)
    return sorted({find(t) for t in ring})


def _bounded_region(
    reach: AbstractSet[Tile], g: Tile, start: Tile, cap: int
) -> frozenset[Tile] | None:
    seen = {start}
    todo = [start]
    while todo:
        x, y = todo.pop()
        for dx, dy in NB8:
            n = (x + dx, y + dy)
            if n != g and n in reach and n not in seen:
                if len(seen) == cap:
                    return None
                seen.add(n)
                todo.append(n)
    return frozenset(seen)


def _matches(reach: Container[Tile], access: Container[Tile], g: Tile, mask: PocketMask) -> bool:
    gx, gy = g
    for dx, dy, free in mask.cells:
        t = (gx + dx, gy + dy)
        if free != (t in reach) or (free and t in access):
            return False
    return True


def _has_exit(reach: Container[Tile], g: Tile, pocket: frozenset[Tile]) -> bool:
    return any(
        (g[0] + dx, g[1] + dy) in reach and (g[0] + dx, g[1] + dy) not in pocket for dx, dy in NB8
    )


def pocket_depths(pocket: frozenset[Tile], mouth: frozenset[Tile]) -> dict[Tile, int]:
    """8-connected BFS distance from `mouth` into `pocket` -- 0 at the tiles nearest the
    entrance, increasing toward the deepest tile. The one piece of pocket geometry
    downstream consumers (the pocket-cache placer, the debug overlay) need beyond
    `find_pockets`' own (pocket, mouth) pair; kept here, next to the search that defines
    what a pocket even is, so nothing downstream has to re-derive pocket membership to
    get it -- a consumer renders/uses this dict, it never recomputes it."""
    sources = [
        (gx + dx, gy + dy) for gx, gy in mouth for dx, dy in NB8 if (gx + dx, gy + dy) in pocket
    ]
    return distances(pocket, sources, NB8)


def dedupe_pockets(
    pockets: Mapping[Tile, tuple[frozenset[Tile], frozenset[Tile]]],
    reach: Container[Tile] = (),
) -> list[list[tuple[Tile, frozenset[Tile], frozenset[Tile]]]]:
    """Collapse near-duplicate mouth candidates into one CANDIDATE LIST per genuine physical
    nook. `find_pockets` returns one entry per candidate MOUTH tile, but several nearby
    tiles each independently qualify as "the" guard spot of the same nook (a corridor
    matches one shorter mask behind every tile along it) -- and in H3 a guard already threatens
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

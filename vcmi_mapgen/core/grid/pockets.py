"""Pocket (sealable-nook) detection and each pocket tile's depth from its mouth."""

import collections
from collections.abc import Collection, Container

from vcmi_mapgen.core.grid.geometry import NB4, NB8
from vcmi_mapgen.core.model import Tile

POCKET_MAX_DIM = 10  # generous bounding-box cap; POCKET_MAX_TILES always binds
# first for any compact shape, so this rarely matters on
# its own -- see find_pockets()
POCKET_MAX_TILES = 10  # user-mandated 2026-09: "a closed cavity of 1 to 10 other
# tiles" (previously 16, from the single-guard-ZoC model
# this replaced)
POCKET_NOOK_BLOCKED = 4  # mouth_key's "in a neck" tiebreak: a mouth tile counts as
# IN the neck when >=4 of its 8 neighbours are blocking

type Pockets = dict[int, dict[Tile, float]]


def _bounded_fill(
    reach: Container[Tile],
    exclude: Container[Tile],
    start: Tile,
    max_dim: int,
    max_tiles: int,
) -> frozenset[Tile] | None:
    """BFS from `start` over `reach - exclude` (`exclude` is a SET of tiles treated as
    blocking). Returns the component as a frozenset if it stays within `max_tiles` cells
    and a `max_dim` x `max_dim` bounding box; returns None the moment it would exceed
    either bound — i.e. it leaked into the wider map rather than being sealed off, so it
    is NOT a pocket.

    8-connected (NB8): H3 heroes move diagonally, so a candidate neck that only blocks
    orthogonal movement is not a real single-entrance enclosure -- the hero just cuts the
    corner and the guard sits in the open next to nothing. Using NB4 here previously made
    ~66% of raw candidates false positives (a diagonal path around the "neck" reconnected
    to the wider map every time)."""
    comp = {start}
    minx = maxx = start[0]
    miny = maxy = start[1]
    q = collections.deque([start])
    while q:
        x, y = q.popleft()
        for dx, dy in NB8:
            m = (x + dx, y + dy)
            if m in exclude or m in comp or m not in reach:
                continue
            comp.add(m)
            minx, maxx = min(minx, m[0]), max(maxx, m[0])
            miny, maxy = min(miny, m[1]), max(maxy, m[1])
            if len(comp) > max_tiles or maxx - minx >= max_dim or maxy - miny >= max_dim:
                return None
            q.append(m)
    return frozenset(comp)


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


def _blocked_neighbours(t: Tile, reach: Container[Tile]) -> int:
    return sum(1 for dx, dy in NB8 if (t[0] + dx, t[1] + dy) not in reach)


def _in_open_field(reach: Container[Tile], m: Tile) -> bool:
    return all((m[0] + ddx, m[1] + ddy) in reach for ddx in range(-2, 3) for ddy in range(-2, 3))


def _doorway_cavity(
    reach: Container[Tile],
    exclude: set[Tile],
    doorway: tuple[Tile, Tile],
    max_dim: int,
    max_tiles: int,
) -> set[Tile]:
    pocket: set[Tile] = set()
    seen = set(exclude)
    for src in doorway:
        for ddx, ddy in NB8:
            s = (src[0] + ddx, src[1] + ddy)
            if s in seen or s not in reach:
                continue
            comp = _bounded_fill(reach, exclude, s, max_dim, max_tiles)
            if comp is None:  # leaked: the open-field side of the doorway
                seen.add(s)
                continue
            seen |= comp
            pocket |= comp
    return pocket


def _pocket_fits(pocket: set[Tile], max_dim: int, max_tiles: int) -> bool:
    if not pocket or len(pocket) > max_tiles:
        return False
    return not (
        max(px for px, _ in pocket) - min(px for px, _ in pocket) >= max_dim
        or max(py for _, py in pocket) - min(py for _, py in pocket) >= max_dim
    )


def find_pockets(
    reach: Collection[Tile], max_dim: int = POCKET_MAX_DIM, max_tiles: int = POCKET_MAX_TILES
) -> dict[Tile, tuple[frozenset[Tile], frozenset[Tile]]]:
    """Geometric pocket detection: small treasure nooks sealable by ONE guard.

    A pocket's mouth is exactly TWO 4-connected tiles — a doorway (user-mandated
    2026-09, replacing the previous single-guard-zone-of-control model). The cavity
    behind a candidate doorway (m1, m2) is the union of 8-connected bounded components
    of `reach - {m1, m2}` seeded next to the doorway (H3 heroes move diagonally, so an
    orthogonal-only block is not a real seal — see `_bounded_fill`); a bounded
    component that stays within `max_tiles` (1..10) counts as part of the cavity, one
    that leaks into the wider map does not (that's simply the "outside" side of the
    doorway, not a rejection of the whole candidate).

    EVERY 4-connected pair in `reach` is tried as a candidate doorway — "try to enlarge
    the cavity by moving the two entrance tiles until it stops being sealed or exceeds
    max_tiles" is achieved by this exhaustive search itself: every alternative doorway
    position for the same physical nook is tried anyway, and `steps.loot.caches.
    dedupe_pockets` + `mouth_key` (unchanged) keep the best (largest, most-in-neck)
    candidate among the overlapping ones.

    Both mouth tiles are always within Chebyshev 1 of each other (4-connected), so a
    guard standing on either one has BOTH inside its own 3x3 zone of control — "the two
    tiles' mouth in the same monster zoc" is automatic, never a filter.

    Returns {guard_tile: (frozenset(pocket_tiles), frozenset(mouth_tiles))} exactly as
    before: mouth_tiles is now always the 2-tile doorway; guard_tile is whichever of
    the two sits more IN the neck (more blocked neighbours — `mouth_key`'s own
    preference, applied here just to pick which one the guard stands on), tied broken
    by tile order."""
    best: dict[frozenset[Tile], tuple[tuple[int, int, int, int, Tile], Tile, frozenset[Tile]]] = {}
    for x, y in sorted(reach):
        for dx, dy in NB4:
            m1, m2 = (x, y), (x + dx, y + dy)
            if m2 <= m1 or m2 not in reach:
                continue  # each unordered pair considered once
            # Cheap skip for the bulk of any open field: with no blocking tile within
            # Chebyshev 2 of EITHER doorway tile, no bounded component can exist.
            if _in_open_field(reach, m1) and _in_open_field(reach, m2):
                continue
            exclude = {m1, m2}
            pocket = _doorway_cavity(reach, exclude, (m1, m2), max_dim, max_tiles)
            if not _pocket_fits(pocket, max_dim, max_tiles):
                continue
            b1, b2 = _blocked_neighbours(m1, reach), _blocked_neighbours(m2, reach)
            guard_tile = m1 if b1 >= b2 else m2
            comp = frozenset(pocket)
            key = mouth_key(reach, guard_tile, comp)
            if comp not in best or key < best[comp][0]:
                best[comp] = (key, guard_tile, frozenset(exclude))
    return {g: (comp, mouth_fs) for comp, (_k, g, mouth_fs) in best.items()}


def pocket_depths(pocket: frozenset[Tile], mouth: frozenset[Tile]) -> dict[Tile, int]:
    """8-connected BFS distance from `mouth` into `pocket` -- 0 at the tiles nearest the
    entrance, increasing toward the deepest tile. The one piece of pocket geometry
    downstream consumers (the pocket-cache placer, the debug overlay) need beyond
    `find_pockets`' own (pocket, mouth) pair; kept here, next to the search that defines
    what a pocket even is, so nothing downstream has to re-derive pocket membership to
    get it -- a consumer renders/uses this dict, it never recomputes it."""
    dist: dict[Tile, int] = {}
    q: collections.deque[Tile] = collections.deque()
    for gx, gy in mouth:
        for dx, dy in NB8:
            nb = (gx + dx, gy + dy)
            if nb in pocket and nb not in dist:
                dist[nb] = 0
                q.append(nb)
    while q:
        t = q.popleft()
        tx, ty = t
        for dx, dy in NB8:
            nb = (tx + dx, ty + dy)
            if nb in pocket and nb not in dist:
                dist[nb] = dist[t] + 1
                q.append(nb)
    return dist

"""Border guards: a hostile guard on every cross-zone crossing left open after the plan."""

import random
from collections.abc import Collection, Container, Mapping, Sequence

from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.models import CoverIndex, PlacedObject, Tile, Zone
from vcmi_mapgen.steps.gate.gates import rnd_monster
from vcmi_mapgen.steps.vegetation.border_plan import blocking_cells, cross_pairs, zone_owner


def guard_crossings(
    W: int,
    H: int,
    grid: Sequence[Sequence[int]],
    zones: Mapping[int, Zone],
    bands: Container[Tile],
    objs: list[PlacedObject],
    hard_avoid: Container[Tile],
    seed: int,
    level: int,
    skip_tiles: Container[Tile] = (),
) -> tuple[list[PlacedObject], set[Tile], int]:
    """Guard every cross-zone crossing that stays open after the vegetation border plan.

    A crossing outside the entrance bands is a back path the plan could not close. A crossing
    inside a band is a planned entrance and must cost a fight. One guard's zone of control
    covers every crossing within Chebyshev 1, so a run of adjacent crossings shares one guard.
    Guards never stand on `hard_avoid` tiles (gameplay cells, approaches, pickups).
    Returns (new_objs, guard_tiles, n_unguarded_pairs)."""
    rng = random.Random(seed ^ 0x6A4D ^ (level * 7919))
    owner, _tname = zone_owner(zones)
    blocked: set[Tile] = set()
    for o in objs:
        blocked.update(blocking_cells(o))
    open_all = {(x, y) for y in range(H) for x in range(W) if grid[y][x] < 8} - blocked
    pairs, band_pairs = cross_pairs(open_all, owner, bands, skip_tiles)
    new_objs: list[PlacedObject] = []
    cover = CoverIndex(objs)

    # Collect existing gameplay guards from objs (placed by pp_gameplay) so the guard
    # pass below avoids duplicating coverage already provided.
    existing_guards = {(o.x, o.y) for o in objs if o.purpose == "GUARD"}

    def _covered(t: Tile, n: Tile, g_set: Collection[Tile]) -> bool:
        return any(
            max(abs(g[0] - t[0]), abs(g[1] - t[1])) <= 1
            or max(abs(g[0] - n[0]), abs(g[1] - n[1])) <= 1
            for g in g_set
        )

    # what must stay open gets contested instead: one hostile guard covers every residual
    # crossing within its Chebyshev-1 zone of control
    decor_blk = OR.decor_blocking_cells(objs + new_objs)

    def _pick_guard(cands: Sequence[Tile]) -> Tile:
        """First candidate whose sprite overlay is clear of decor; else the first."""
        rnd = rnd_monster(3)
        for c in cands:
            if OR.overlay_clear(rnd.mask, c[0], c[1], decor_blk):
                return c
        return cands[0]

    def _stand_guard(cands: Sequence[Tile]) -> PlacedObject | None:
        first = _pick_guard(cands)
        for g in [first, *(c for c in cands if c != first)]:
            gident = rnd_monster(3 + (1 if rng.random() < 0.3 else 0))
            guard = PlacedObject.at(
                gident, g[0], g[1], level=0, purpose="GUARD", options={"character": "hostile"}
            )
            if cover.try_add(guard):
                return guard
        return None

    guard_tiles: set[Tile] = set()
    unguarded = 0
    for t, n in pairs:
        if _covered(t, n, guard_tiles | existing_guards):
            continue
        cands = [c for c in sorted((t, n)) if c not in hard_avoid]
        if not cands:
            unguarded += 1
            continue
        guard = _stand_guard(cands)
        if guard is None:
            unguarded += 1
            continue
        guard.seal = True
        new_objs.append(guard)  # informational: dup-guard cleanup must
        guard_tiles.add((guard.x, guard.y))  # never drop it — it IS the border

    # Band pairs (planned entrance corridors) were left open on purpose but every corridor
    # must have at least one guard so the crossing requires a fight.  If pp_gameplay already
    # placed a guard that covers the pair, skip it; otherwise add one now.
    band_guard_tiles: set[Tile] = set()
    for t, n in band_pairs:
        if _covered(t, n, guard_tiles | existing_guards | band_guard_tiles):
            continue
        cands = [c for c in sorted((t, n)) if c not in hard_avoid]
        if not cands:
            continue
        guard = _stand_guard(cands)
        if guard is None:
            continue
        guard.seal = True
        new_objs.append(guard)
        band_guard_tiles.add((guard.x, guard.y))

    guard_tiles |= band_guard_tiles
    return new_objs, guard_tiles, unguarded

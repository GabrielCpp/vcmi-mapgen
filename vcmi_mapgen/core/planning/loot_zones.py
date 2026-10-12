"""The loot zones of a map: the small zones with a single passage that a gate or a monolith
pair seals, drawn at random among the candidates up to the corpus count of each. The choice is
made once, after vegetation, so the door guards, the gameplay objects and the seals all read
the same zones."""

from __future__ import annotations

import random
from collections.abc import Iterable, Mapping
from collections.abc import Set as AbstractSet

from vcmi_mapgen.core.grid.reach import STEPS8, reach
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.placement.ground import Ground

LOOT_ZONE_MAX_TILES = 60
NO_ZONES: frozenset[int] = frozenset()


def _nbs(t: Tile) -> Iterable[Tile]:
    return ((t[0] + dx, t[1] + dy) for dx, dy in STEPS8)


def _clusters(tiles: AbstractSet[Tile]) -> int:
    seen: set[Tile] = set()
    n = 0
    for t in sorted(tiles):
        if t not in seen:
            n += 1
            seen |= reach(tiles, [t], STEPS8)
    return n


def passage(
    ts: AbstractSet[Tile], all_ts: AbstractSet[Tile], blocked: AbstractSet[Tile]
) -> tuple[int, frozenset[Tile]]:
    """The open tiles of ``ts`` that touch an open tile of another zone, and how many
    8-connected clusters they form."""
    ext = (all_ts - ts) - blocked
    boundary = frozenset(t for t in ts - blocked if any(nb in ext for nb in _nbs(t)))
    return _clusters(boundary), boundary


def neighbour_zones(
    ts: AbstractSet[Tile], zone_of: Mapping[Tile, int], blocked: AbstractSet[Tile]
) -> frozenset[int]:
    """The zones an open tile of ``ts`` touches across an open tile."""
    return frozenset(
        zone_of[nb]
        for t in ts - blocked
        for nb in _nbs(t)
        if nb not in ts and nb not in blocked and nb in zone_of
    )


def on_coast(ts: AbstractSet[Tile], blocked: AbstractSet[Tile], ground: Ground) -> bool:
    """Whether an open tile of ``ts`` touches water, where a boat could land."""
    if not ground:
        return False
    h, w = len(ground), len(ground[0])
    return any(
        0 <= nx < w and 0 <= ny < h and Terrain(ground[ny][nx]).is_water
        for t in ts - blocked
        for nx, ny in _nbs(t)
    )


def choose_loot_zones(
    zones: Mapping[int, AbstractSet[Tile]],
    blocked: AbstractSet[Tile],
    ground: Ground = (),
    skip: AbstractSet[int] = NO_ZONES,
) -> frozenset[int]:
    """The zones of one level a seal will close: each holds at most ``LOOT_ZONE_MAX_TILES``
    tiles and an open tile, opens onto exactly one other zone through one passage, touches
    no water and is not in ``skip``."""
    all_ts = frozenset[Tile]().union(*zones.values())
    zone_of = {t: zid for zid, ts in zones.items() for t in ts}
    return frozenset(
        zid
        for zid, ts in sorted(zones.items())
        if zid not in skip
        and len(ts) <= LOOT_ZONE_MAX_TILES
        and bool(ts - blocked)
        and len(neighbour_zones(ts, zone_of, blocked)) == 1
        and not on_coast(ts, blocked, ground)
        and passage(ts, all_ts, blocked)[0] == 1
    )


type LevelZones = dict[int, frozenset[int]]


def _by_level(drawn: Iterable[tuple[int, int]], levels: Iterable[int]) -> LevelZones:
    out = {lvl: set[int]() for lvl in levels}
    for lvl, zid in drawn:
        out[lvl].add(zid)
    return {lvl: frozenset(zids) for lvl, zids in out.items()}


def draw_loot_zones(
    candidates: Mapping[int, AbstractSet[int]], gates: int, pairs: int, rng: random.Random
) -> tuple[LevelZones, LevelZones]:
    """The candidate zones of every level drawn at random, ``gates`` to seal behind a gate and
    ``pairs`` behind a monolith pair, the gates served first when the candidates run short.
    Returns every drawn zone by level, then the zones among them a monolith pair seals."""
    pool = sorted((lvl, zid) for lvl, zids in candidates.items() for zid in zids)
    rng.shuffle(pool)
    drawn = pool[: gates + pairs]
    return _by_level(drawn, candidates), _by_level(drawn[gates:], candidates)

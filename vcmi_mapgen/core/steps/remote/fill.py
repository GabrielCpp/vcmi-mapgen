"""One level's remote fill: a landmark in every run of free land farther than the remote
distance from every object worth the walk, the largest run first, down to a pickup."""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import cast

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.components import components
from vcmi_mapgen.core.model import Identity, PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.placement.fallback import smaller
from vcmi_mapgen.core.placement.site import LevelField, SiteZone, ZoneFooting, ZoneSite
from vcmi_mapgen.core.planning.landmarks import (
    ABANDONED_MINE,
    DWELLING,
    STAT_BUILDING,
    kind_order,
    landmark_pool,
)
from vcmi_mapgen.core.reading.remote import free_land, level_distance, remote_runs

REMOTE_SALT = 0x7E40
LADDER = (ABANDONED_MINE, STAT_BUILDING, DWELLING)


@dataclass(frozen=True, slots=True)
class RemoteLevel:
    """What one level's remote fill reads: the level, its terrain grid, its objects, the zone
    of each tile, what each zone brings to placement, the level field the sites share, the
    approaches every new body keeps off, the tiles earlier steps claimed, and the remote
    distance."""

    level: int
    grid: Sequence[Sequence[int]]
    objs: Sequence[PlacedObject]
    zone_of: Mapping[Tile, int]
    zones: Mapping[int, SiteZone]
    lf: LevelField
    kept: frozenset[Tile]
    claims: frozenset[Tile]
    far: int


@dataclass(frozen=True, slots=True)
class RemoteFill:
    """One level's new objects in placement order, guards included, and one log line per
    run left empty."""

    objs: tuple[PlacedObject, ...]
    log: tuple[str, ...]


def approaches(
    objs: Sequence[PlacedObject], unwalkable: AbstractSet[Tile], size: int
) -> frozenset[Tile]:
    """The walkable tiles on the map beside the door of every object with a purpose, guards
    aside: a hero fights a guard on its own tile."""
    out: set[Tile] = set()
    for o in objs:
        if not o.purpose or o.purpose in (
            Purpose.DECORATION,
            Purpose.TERRAIN_MODIFIER,
            Purpose.GUARD,
        ):
            continue
        for (x, y), role in o.footprint.at(o.x, o.y):
            if role.interactive:
                out.update(
                    t
                    for dx in (-1, 0, 1)
                    for dy in (-1, 0, 1)
                    if 0 <= (t := (x + dx, y + dy))[0] < size
                    and 0 <= t[1] < size
                    and t not in unwalkable
                )
    return frozenset(out)


def landings(
    passable: AbstractSet[Tile],
    prot: AbstractSet[Tile],
    grid: Sequence[Sequence[int]],
    unwalkable: AbstractSet[Tile],
) -> frozenset[Tile]:
    """The tiles where a hero steps onto each part of a zone's walkable land that the zone's
    web never reaches: the tiles beside water, or beside walkable land of another zone."""
    size = len(grid)
    comp = components(set(passable))
    webbed = {comp[t] for t in prot if t in comp}
    out: set[Tile] = set()
    for t in passable:
        if comp[t] in webbed:
            continue
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                n = (t[0] + dx, t[1] + dy)
                if n in passable or not (0 <= n[0] < size and 0 <= n[1] < size):
                    continue
                if grid[n[1]][n[0]] == Terrain.WATER or n not in unwalkable:
                    out.add(t)
    return frozenset(out)


def spot_order(tiles: frozenset[Tile], distance: NDArray[np.int64]) -> list[Tile]:
    """The tiles farthest from every object worth the walk first, in tile order on a tie."""
    depth = cast(list[list[int]], distance.tolist())
    return sorted(tiles, key=lambda t: (-depth[t[1]][t[0]], t))


def _piles(site: ZoneSite, terrain: str, rng: random.Random) -> list[Identity]:
    pool = list(site.catalog.candidates(Purpose.RESOURCE_PILE, terrain))
    rng.shuffle(pool)
    return sorted(pool, key=lambda i: len(i.footprint.cells), reverse=True)


def stand_remote(
    site: ZoneSite, tiles: Sequence[Tile], terrain: str, rng: random.Random
) -> PlacedObject | None:
    """Stand one landmark on ``tiles``, whose ground is ``terrain``: the drawn kind first, a
    smaller object of the same kind next, then the next kind, and a pickup last."""
    for kind in kind_order(rng, LADDER):
        pool = landmark_pool(site.catalog, kind, terrain)
        if not pool:
            continue
        footing = ZoneFooting(mine=kind.purpose == Purpose.MINE)
        first = rng.choice(pool)
        for ident in (first, *smaller(site, pool, first)):
            obj = site.place(kind.purpose, ident, tiles, footing)
            if obj is not None:
                return obj
    for ident in _piles(site, terrain, rng):
        obj = site.place(Purpose.RESOURCE_PILE, ident, tiles)
        if obj is not None:
            return obj
    return None


def _site(
    catalog: Catalog, lv: RemoteLevel, sites: dict[int, ZoneSite], zid: int, seed: int
) -> ZoneSite:
    if zid not in sites:
        site = ZoneSite(catalog, zid, lv.zones[zid], lv.lf, seed ^ REMOTE_SALT)
        site.reserved |= lv.kept
        sites[zid] = site
    return sites[zid]


def _claimed(size: int, claims: frozenset[Tile]) -> NDArray[np.bool_]:
    mask = np.zeros((size, size), dtype=np.bool_)
    for x, y in claims:
        mask[y, x] = True
    return mask


def fill_level(catalog: Catalog, lv: RemoteLevel, seed: int) -> RemoteFill:
    """Fill the level's remote runs one spot at a time, reading the runs again after each
    landmark. A zone's share of a run with no room is logged and left."""
    size = len(lv.grid)
    claimed = _claimed(size, lv.claims)
    sites: dict[int, ZoneSite] = {}
    failed: set[Tile] = set()
    log: list[str] = []
    while True:
        new = [o for _z, s in sorted(sites.items()) for o in s.objs]
        objs = [*lv.objs, *new]
        distance = level_distance(objs, size)
        free = free_land(lv.grid, objs) & ~claimed
        runs = [r.tiles - failed for r in remote_runs(distance, free, lv.far)]
        left = next((frozenset(t) for t in runs if t), None)
        if left is None:
            return RemoteFill(tuple(new), tuple(log))
        heart = spot_order(left, distance)[0]
        zid = lv.zone_of.get(heart)
        spot = frozenset(t for t in left if lv.zone_of.get(t) == zid)
        placed = None
        if zid is not None and zid in lv.zones:
            site = _site(catalog, lv, sites, zid, seed)
            terrain = catalog.terrain_name(lv.grid[heart[1]][heart[0]])
            hx, hy = heart
            rng = random.Random(seed ^ REMOTE_SALT ^ (lv.level * 7919) ^ (hx * 104729 + hy))
            placed = stand_remote(site, spot_order(spot, distance), terrain, rng)
        if placed is None:
            failed |= spot
            log.append(
                f"  L{lv.level} zone {zid}: remote run at {heart} left empty ({len(spot)} tiles)"
            )

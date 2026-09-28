"""The special reward hoard a portal-rescued zone holds: dense resource piles reachable
from the portal entry and one interior guard."""

import random
from dataclasses import dataclass
from functools import partial

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.geometry import centre_key
from vcmi_mapgen.core.grid.reach import entry_reach
from vcmi_mapgen.core.model import CoverIndex, PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement.guards import rnd_monster
from vcmi_mapgen.core.placement.place import PlaceSpec, PlaceTarget, place_one
from vcmi_mapgen.core.planning.zone_index import ZoneRecord
from vcmi_mapgen.corpus.gameplay import load_gameplay


@dataclass(frozen=True, slots=True)
class RewardSite:
    """Where a reward hoard goes: the rescued zone's record, the portal's entry tile,
    the map bounds and the level's cover index."""

    zr: ZoneRecord
    entry: Tile
    cover: CoverIndex
    bounds: tuple[int, int] | None = None


def place_reward_zone(catalog: Catalog, site: RewardSite, seed: int = 1) -> list[PlacedObject]:
    """SPECIAL REWARD upgrade for a zone rescued by a guarded two-way monolith (pp_map's
    unreachable-zone pass): the pocket-cache grammar scaled to the whole zone — dense
    resource piles (all `cache`-tagged) reachable from the portal's `entry` tile, plus one
    interior guard whose strength tracks the accumulated value (the cache ladder + 1).
    Resources only — an artifact pickup used to be part of this hoard, but artifacts are
    pocket/loot-zone only now (a portal-rescued zone is neither), so those slots are
    additional resource piles instead; same total item count, same guard mechanic. Works
    both for fully-populated zones (extra richness) and for bare sub-MIN_AREA slivers the
    level pass skipped (their only content). Claims its cells in the cover index so the
    later pocket-cache pass never double-stacks. Returns objs."""
    zr, entry, bounds, cover = site.zr, site.entry, site.bounds, site.cover
    terrain = zr.terrain
    st = load_gameplay()[terrain]
    rng = random.Random(seed ^ (entry[0] * 92821) ^ (entry[1] * 131071) ^ 0x907A1)
    ts = zr.ts
    area = len(ts)

    # reach: what the portal's entry tile actually opens up (4-connected within passable)
    reach = entry_reach(zr.passable, entry)
    if not reach:
        return []

    n_res = max(4, area // 10) + max(2, area // 25)
    pool_res = catalog.candidates(Purpose.RESOURCE_PILE, terrain)
    objs: list[PlacedObject] = []
    val = 0

    spots = sorted(reach - cover.claims)
    rng.shuffle(spots)
    for t in spots:
        if n_res <= 0:
            break
        if place_one(
            PlaceTarget(catalog, objs, cover, reach, rng, st, bounds=bounds),
            PlaceSpec(Purpose.RESOURCE_PILE, pool_res, cache=True),
            t[0],
            t[1],
        ):
            n_res -= 1
            val += 2

    if objs:
        # one interior guard near the zone's own centre: the portal guard gates entry, this
        # one gates the hoard itself — cache ladder (pp_pickup pocket convention) + 1
        cx = sum(x for x, _ in ts) / area
        cy = sum(y for _, y in ts) / area
        lvl = 1 + (val >= 4) + (val >= 7) + (val >= 10) + (val >= 13) + 1
        gident = rnd_monster(catalog, lvl)
        for t in sorted(reach - cover.claims, key=partial(centre_key, cx=cx, cy=cy)):
            if place_one(
                PlaceTarget(catalog, objs, cover, reach, rng, st, bounds=bounds),
                PlaceSpec(Purpose.GUARD, None, ident=gident),
                t[0],
                t[1],
            ):
                break
    return objs

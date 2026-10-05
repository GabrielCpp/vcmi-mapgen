"""The prizes of a portal place: priced by the effort to carry them home through the portal,
counted by the place's size, and guarded only by the guard at the near portal."""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.reach import entry_reach
from vcmi_mapgen.core.model import PlacedObject
from vcmi_mapgen.core.placement.place import PlaceTarget
from vcmi_mapgen.core.placement.prizes import PrizePools, place_prizes
from vcmi_mapgen.core.planning.pricing import (
    CutoffPlace,
    Opener,
    PrizeCount,
    UnreachedPlaceError,
    price_at,
    rewards_in,
)
from vcmi_mapgen.core.priors.effort import EffortPriors
from vcmi_mapgen.core.reading.effort import EffortMap
from vcmi_mapgen.core.reading.routes import Spot
from vcmi_mapgen.core.steps.portal.rescue import PortalWorld, Rescued


@dataclass(frozen=True, slots=True)
class HoardPricing:
    """The effort map with the portals on it, the band offers and each level's prize count."""

    em: EffortMap
    effort: EffortPriors
    counts: Mapping[int, PrizeCount]


def fill_hoard(
    catalog: Catalog, world: PortalWorld, rescued: Rescued, pricing: HoardPricing, seed: int
) -> CutoffPlace:
    """Price one rescued zone at the cheapest tile its portal opens, and place its prizes
    there from the band's offer. Raises ``UnreachedPlaceError`` when no home reaches it."""
    zr, lvl, entry = rescued.record, rescued.level, rescued.entry
    reach = frozenset(entry_reach(zr.passable, entry))
    price = price_at(pricing.em, pricing.effort, (Spot(lvl, *t) for t in reach))
    if price is None:
        raise UnreachedPlaceError(f"no home reaches portal zone {zr.zid} on level {lvl}")
    rng = random.Random(seed ^ (entry[0] * 92821) ^ (entry[1] * 131071) ^ 0x907A1)
    cover = world.covers[lvl]
    objs = world.objs_by_level[lvl]
    held = rewards_in(catalog, objs, zr.ts)
    count = pricing.counts.get(lvl, PrizeCount()).count(len(zr.ts), held)
    placed: list[PlacedObject] = []
    target = PlaceTarget(
        catalog, placed, cover, reach, rng, world.gameplay[zr.terrain], (world.size, world.size)
    )
    tiles = sorted(reach - cover.claims)
    rng.shuffle(tiles)
    offer = pricing.effort.offer(price.band)
    prizes = place_prizes(target, PrizePools.of(catalog, zr.terrain), offer, tiles, count)
    for o in placed:
        o.level = lvl
    objs.extend(placed)
    world.targets_by_level[lvl].extend(sorted(prizes.took()))
    slot = (prizes.held.at(lvl, zr.terrain),) if prizes.held else ()
    return CutoffPlace(Opener.PORTAL, price, tuple(placed), slot)


def fill_hoards(
    catalog: Catalog,
    world: PortalWorld,
    rescued: Sequence[Rescued],
    pricing: HoardPricing,
    seed: int,
) -> dict[int, dict[int, CutoffPlace]]:
    """Every rescued zone's place, per level and zone id."""
    places: dict[int, dict[int, CutoffPlace]] = {}
    for r in rescued:
        places.setdefault(r.level, {})[r.record.zid] = fill_hoard(catalog, world, r, pricing, seed)
    return places

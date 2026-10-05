"""Price each sealed loot zone by the effort a hero spends to carry its reward home."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from vcmi_mapgen.core.model import PlacedObject
from vcmi_mapgen.core.planning.pricing import Price, UnreachedPlaceError, price_at
from vcmi_mapgen.core.planning.zone_index import ZoneRecord
from vcmi_mapgen.core.priors.effort import EffortPriors
from vcmi_mapgen.core.reading.effort import EffortMap
from vcmi_mapgen.core.reading.routes import Spot
from vcmi_mapgen.core.steps.gated.result import LootAccess


def price_places(
    em: EffortMap,
    access: Mapping[int, Mapping[int, LootAccess]],
    effort: EffortPriors,
) -> dict[int, dict[int, Price]]:
    """The price of every loot zone, per level and zone id, read at its access visit tiles.
    A loot zone no home reaches raises ``UnreachedPlaceError``."""
    out: dict[int, dict[int, Price]] = {level: {} for level in access}
    for level, zones in access.items():
        for zid, acc in zones.items():
            price = price_at(em, effort, (Spot(level, x, y) for x, y in acc.interactive))
            if price is None:
                raise UnreachedPlaceError(f"no home reaches loot zone {zid} on level {level}")
            out[level][zid] = price
    return out


def prizes(
    zone_records: Sequence[ZoneRecord], objs: Sequence[PlacedObject]
) -> dict[int, tuple[PlacedObject, ...]]:
    """The objects standing in each zone, by zone id."""
    return {zr.zid: tuple(o for o in objs if (o.x, o.y) in zr.ts) for zr in zone_records}

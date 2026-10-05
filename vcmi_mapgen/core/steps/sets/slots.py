"""The held prize slots the set dealer deals onto, each priced in hero-days from the nearest
home."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.placement.prizes import HeldPrize
from vcmi_mapgen.core.priors.effort import EffortPriors
from vcmi_mapgen.core.reading.effort import effort_map
from vcmi_mapgen.core.reading.homes import town_homes
from vcmi_mapgen.core.reading.routes import Spot, route_map

NO_HOME = -1


@dataclass(frozen=True, slots=True)
class Slot:
    """A held prize slot, the band and effort of its cheapest home, and that home's index.
    A slot no home reaches has band 0 and ``NO_HOME``."""

    held: HeldPrize
    band: int
    effort: int
    home: int


def price_slots(
    catalog: Catalog, map_state: MapState, held: Sequence[HeldPrize], effort: EffortPriors
) -> list[Slot]:
    """Every held slot priced from each town on its own, keeping the cheapest town."""
    route = route_map(catalog, map_state)
    maps = [effort_map(route, spots, effort.toll) for spots in town_homes(map_state)]
    slots: list[Slot] = []
    for h in held:
        spot = Spot(h.level, *h.tile)
        found = [(e.total, i) for i, em in enumerate(maps) if (e := em.at(spot)) is not None]
        if not found:
            slots.append(Slot(h, 0, 0, NO_HOME))
            continue
        total, home = min(found)
        slots.append(Slot(h, effort.band(total), total, home))
    return slots

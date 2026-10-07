"""The zone economy: the mines every map must cover, the mine sprites a terrain shows, and
the dwellings tied to their nearest town."""

import math
from collections.abc import Mapping, Sequence

from vcmi_mapgen.core.catalog import Catalog, Trait
from vcmi_mapgen.core.model import Dwelling, Identity, MapState, PlacedObject
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.reading.effort import EffortMap, effort_map
from vcmi_mapgen.core.reading.homes import town_spots
from vcmi_mapgen.core.reading.promise import doors
from vcmi_mapgen.core.reading.routes import route_map

# the six basic resource mines every map must cover (gold is the deliberate exception:
# only worth placing when the map holds several towns)
BASIC_MINE_RES = ("sawmill", "orePit", "alchemistLab", "sulfurDune", "crystalCavern", "gemPond")

GOLD = "goldMine"


def mine_variants(ids: list[Identity], mine_w: Mapping[str, int]) -> list[Identity]:
    """Terrain-faithful sprite variants: mine DEFs carry a baked-in terrain apron
    (avmgogr0 grass vs avmgold0 dirt), so keep only the variants mapmakers actually
    use on THIS terrain (>= 20% of the top variant's corpus weight — drops the rare
    cross-terrain leakage that put dirt-apron mines on grass)."""
    ws = {i.kind.lower(): mine_w.get(i.kind.lower(), 0) for i in ids}
    top = max(ws.values(), default=0)
    if top > 0:
        keep = [i for i in ids if ws[i.kind.lower()] >= 0.2 * top]
        return keep or ids
    return ids


def _distance(em: EffortMap, town: PlacedObject, obj: PlacedObject) -> tuple[float, int, int]:
    walks = [e.days for d in doors(obj) if (e := em.visit(d, len(em.toll) - 1)) is not None]
    days = min(walks, default=math.inf)
    apart = abs(town.x - obj.x) + abs(town.y - obj.y)
    return (days, int(town.level != obj.level), apart)


def tie_dwellings(catalog: Catalog, map_state: MapState, toll: Sequence[int]) -> None:
    # tie each RANDOM dwelling to the town, neutral or not, a hero walks to it from in the
    # fewest days, guards aside: VCMI's `sameAsTown` link makes the dwelling resolve to the
    # town's (lobby-picked) faction at game start, so the creatures around a random town are
    # its own. A dwelling no town reaches ties to the nearest town in a straight line.
    # Instance names are minted only at export, so the marker carries the town's
    # coordinates; `vcmi.export.build_document` swaps in the instanceName.
    towns = [o for o in map_state.objs if o.purpose == Purpose.TOWN]
    randoms = catalog.types_with(Trait.RANDOM_DWELLING)
    dwellings = [o for o in map_state.objs if catalog.identity_of(o.kind).type in randoms]
    if not towns or not dwellings:
        return
    route = route_map(catalog, map_state)
    maps = [effort_map(route, town_spots(t), toll) for t in towns]
    for o in dwellings:
        _em, town = min(zip(maps, towns, strict=True), key=lambda p: _distance(p[0], p[1], o))
        o.payload = Dwelling((town.x, town.y, town.level))

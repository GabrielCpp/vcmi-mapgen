"""The zone economy: the mines every map must cover, the mine sprites a terrain shows, and
the dwellings tied to a zone's town."""

from collections.abc import Iterable, Mapping

from vcmi_mapgen.core.catalog import Catalog, Trait
from vcmi_mapgen.core.model import Dwelling, Identity, PlacedObject
from vcmi_mapgen.core.model.purpose import Purpose

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


def tie_dwellings(catalog: Catalog, objs: Iterable[PlacedObject]) -> None:
    # tie the zone's RANDOM dwellings to its town: VCMI's `sameAsTown` link makes the
    # dwelling resolve to the town's (lobby-picked) faction at game start, so the creatures
    # around a random town are its own. Instance names are minted only at export, so the
    # marker carries the town's coordinates; `vcmi.export.build_document` swaps
    # in the instanceName.
    town = next((o for o in objs if o.purpose == Purpose.TOWN), None)
    if town is not None:
        for o in objs:
            if catalog.identity_of(o.kind).type in catalog.types_with(Trait.RANDOM_DWELLING):
                o.payload = Dwelling((town.x, town.y, town.level))

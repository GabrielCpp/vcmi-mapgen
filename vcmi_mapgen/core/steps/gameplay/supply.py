"""Each town's own sawmill and ore pit, stood whatever already stands near it: per town and
supply resource, the first mine variant that fits on a site of the town's level with its
entrance within NEAR tiles of the town's, the town's nearest sites first."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.model import Identity, PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement.guards import Fit
from vcmi_mapgen.core.placement.site import Footing, ZoneSite, door_cells, footing_of
from vcmi_mapgen.core.reading.families import mine_family
from vcmi_mapgen.core.reading.supply import NEAR, SUPPLY, apart, entrance
from vcmi_mapgen.core.steps.gameplay.allocate import Variants, promised_guard

type Supply = Callable[[Sequence[PlacedObject]], list[tuple[str, PlacedObject]]]


@dataclass(frozen=True, slots=True)
class NearFooting:
    """The mine footing, trying only the anchors whose entrances lie within NEAR tiles of
    ``door``."""

    inner: Footing
    door: Tile

    def admits(self, site: ZoneSite, ident: Identity, anchor: Tile) -> bool:
        cells = door_cells(ident.footprint, anchor) or [anchor]
        near = all(apart(c, self.door) <= NEAR for c in cells)
        return near and self.inner.admits(site, ident, anchor)

    def fit(self, site: ZoneSite, ident: Identity, anchor: Tile) -> Fit | None:
        return self.inner.fit(site, ident, anchor)


def supply_spots(
    sites: Sequence[ZoneSite], town: PlacedObject
) -> list[tuple[ZoneSite, list[Tile]]]:
    """The sites on the town's level with tiles within NEAR of its entrance, nearest first,
    each with those tiles nearest first."""
    door = entrance(town)
    found: list[tuple[int, int, ZoneSite, list[Tile]]] = []
    for site in sites:
        if site.lf.level != town.level:
            continue
        near = sorted((d, t) for t in site.ts if (d := apart(t, door)) <= NEAR)
        if near:
            found.append((near[0][0], site.zid, site, [t for _d, t in near]))
    return [(site, tiles) for _d, _zid, site, tiles in sorted(found, key=lambda f: f[:2])]


def _stand(
    spots: Sequence[tuple[ZoneSite, list[Tile]]], variants: Variants, footing: Footing, res: str
) -> PlacedObject | None:
    for site, tiles in spots:
        for ident in variants(site, res):
            obj = site.place(Purpose.MINE, ident, tiles, footing, promised_guard(res))
            if obj is not None:
                return obj
    return None


def stand_pairs(
    sites: Sequence[ZoneSite], variants: Variants, towns: Sequence[PlacedObject]
) -> list[tuple[str, PlacedObject]]:
    """One sawmill and one ore pit per town of ``towns``, in level then tile order, each
    with its family. A town whose surroundings take no mine of a resource goes without."""
    stood: list[tuple[str, PlacedObject]] = []
    for town in sorted(towns, key=lambda t: (t.level, t.x, t.y)):
        spots = supply_spots(sites, town)
        footing = NearFooting(footing_of(Purpose.MINE), entrance(town))
        for res in SUPPLY:
            obj = _stand(spots, variants, footing, res)
            if obj is not None:
                stood.append((mine_family(res), obj))
    return stood

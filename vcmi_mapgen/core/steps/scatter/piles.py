"""One level's free resource piles, zone by zone, outside every loot zone."""

from __future__ import annotations

import collections
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.segment import ZoneLabel
from vcmi_mapgen.core.model import CoverIndex, PlacedObject, Tile
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.placement import scatter as SC
from vcmi_mapgen.core.placement.guards import guard_zoc
from vcmi_mapgen.core.placement.site import PlacedZone
from vcmi_mapgen.core.planning.zone_index import ZoneRecord
from vcmi_mapgen.core.planning.zone_plan import PlanLevel


@dataclass(frozen=True, slots=True)
class PileLevel:
    """What one level's scatter reads: its zone records, its plan, each zone after
    placement, the zone label grid, and the tiles earlier steps claimed."""

    level: int
    records: Sequence[ZoneRecord]
    plan: PlanLevel
    placed: Mapping[int, PlacedZone]
    label: ZoneLabel
    claims: frozenset[Tile]


@dataclass(frozen=True, slots=True)
class Piles:
    """One level's piles in placement order, and one log line per zone scattered."""

    objs: tuple[PlacedObject, ...]
    log: tuple[str, ...]


def scatter_level(
    catalog: Catalog, lv: PileLevel, level_objs: Sequence[PlacedObject], seed: int, size: int
) -> Piles:
    """Scatter piles into each zone that is not a loot zone. A pile never covers a tile an
    earlier object covers or claimed, and never sits inside a guard's zone of control."""
    taken = {
        (cx, cy) for o in level_objs for cx, cy, _b in FP.anchored_cells(o.footprint, o.x, o.y)
    }
    cover = CoverIndex(level_objs, lv.claims | taken)
    zoc = guard_zoc(level_objs)
    objs: list[PlacedObject] = []
    log: list[str] = []
    for zr in lv.records:
        if zr.loot_zone:
            continue
        zone = lv.plan.zones[zr.zid]
        pz = lv.placed[zr.zid]
        piles, _r = SC.place_scatter(
            catalog,
            SC.ScatterZone(
                zone.ts,
                lv.label,
                zr.zid,
                zone.terrain,
                pz.open_set - (zone.rim8 - zone.ent_bands),
                pz.prot,
                entrances=list(zone.entrances),
            ),
            SC.ScatterConfig(
                seed=seed, bounds=(size, size), cover=cover, reach_in=set(zr.reach), avoid=zoc
            ),
        )
        for o in piles:
            o.level = lv.level
        objs.extend(piles)
        pk = collections.Counter(o.purpose for o in piles)
        log.append(
            f"  L{lv.level} zone {zr.zid:>3} {zone.terrain:<8} {len(zone.ts):>5} tiles: "
            + f"scatter res={pk.get('RESOURCE_PILE', 0)}"
        )
    return Piles(tuple(objs), tuple(log))

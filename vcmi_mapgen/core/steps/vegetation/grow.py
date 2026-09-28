"""One level's vegetation, grown zone by zone before the border seal."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.segment import ZoneLabel
from vcmi_mapgen.core.model import PlacedObject, Tile
from vcmi_mapgen.core.planning.zone_plan import PlanLevel, ZonePlan
from vcmi_mapgen.core.steps.vegetation import sample as PP
from vcmi_mapgen.core.steps.vegetation.result import VegetatedZone


@dataclass(frozen=True, slots=True)
class GrowLevel:
    """What one level's growing reads: its plan, each zone's centroid, the zone label grid,
    and the tiles already taken before any tree grows."""

    level: int
    plan: PlanLevel
    centroids: Mapping[int, tuple[float, float]]
    label: ZoneLabel
    taken: frozenset[Tile]


@dataclass(frozen=True, slots=True)
class Grown:
    """One level's new vegetation in placement order, and each zone's open and passable
    tiles before the seal."""

    objs: tuple[PlacedObject, ...]
    zones: Mapping[int, VegetatedZone]


def vegetation_models(catalog: Catalog, plan: ZonePlan) -> dict[str, PP.VegModel]:
    """One fitted model per terrain the plan holds, built in the order the zones name them."""
    models: dict[str, PP.VegModel] = {}
    for pl in plan.levels.values():
        for zone in pl.zones.values():
            if zone.terrain not in models:
                models[zone.terrain] = PP.build_model(catalog, zone.terrain)
    return models


def grow_level(models: Mapping[str, PP.VegModel], lv: GrowLevel, seed: int) -> Grown:
    """Grow each zone's vegetation off the taken tiles, the landings and the town room, and
    densify it along the rim outside the entrance bands. A zone whose terrain has no
    vegetation category keeps an empty ``VegetatedZone``."""
    landings = lv.plan.landings.blk | lv.plan.landings.appr
    objs: list[PlacedObject] = []
    zones: dict[int, VegetatedZone] = {}
    for zid, zone in lv.plan.zones.items():
        model = models[zone.terrain]
        if not model.cats:
            zones[zid] = VegetatedZone()
            continue
        seaport = landings & zone.ts
        forbid = lv.taken | seaport | zone.town.clear
        zobjs, blocked, _ = PP.sample_zone(
            PP.ZoneRef(zone.ts, lv.label, zid, lv.centroids[zid], lv.level),
            model,
            seed=seed,
            opts=PP.SampleOptions(
                prot=zone.prot,
                forbid=forbid,
                border=frozenset(zone.rim8 - zone.ent_bands - forbid),
                impassable=zone.town.blk,
            ),
        )
        objs.extend(zobjs)
        zones[zid] = VegetatedZone(
            open_set=frozenset(zone.ts - blocked - seaport),
            passable=frozenset(zone.ts - blocked),
        )
    return Grown(tuple(objs), zones)

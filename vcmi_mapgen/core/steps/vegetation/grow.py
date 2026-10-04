"""One level's vegetation, grown zone by zone before the border seal."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.segment import ZoneLabel
from vcmi_mapgen.core.model import PlacedObject, Tile
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.planning.web import ZoneRef
from vcmi_mapgen.core.planning.zone_plan import PlanLevel, ZonePlan
from vcmi_mapgen.core.priors.vegetation import VegetationStats
from vcmi_mapgen.core.steps.vegetation.model import VegModel, build_model
from vcmi_mapgen.core.steps.vegetation.result import VegetatedZone
from vcmi_mapgen.core.steps.vegetation.sampler import SampleOptions, Sampler


@dataclass(frozen=True, slots=True)
class GrowLevel:
    """What one level's growing reads: its plan, each zone's centroid, the zone label grid,
    the tiles already taken before any tree grows, and the level's terrain grid every tree
    must be allowed on. An empty ``ground`` checks no terrain."""

    level: int
    plan: PlanLevel
    centroids: Mapping[int, tuple[float, float]]
    label: ZoneLabel
    taken: frozenset[Tile]
    ground: Sequence[Sequence[Terrain]] = ()


@dataclass(frozen=True, slots=True)
class Grown:
    """One level's new vegetation in placement order, and each zone's open and passable
    tiles before the seal."""

    objs: tuple[PlacedObject, ...]
    zones: Mapping[int, VegetatedZone]


def vegetation_models(
    catalog: Catalog, stats: Mapping[str, VegetationStats], plan: ZonePlan
) -> dict[str, VegModel]:
    """One fitted model per terrain the plan holds, built from that terrain's ``stats`` in
    the order the zones name them."""
    models: dict[str, VegModel] = {}
    for pl in plan.levels.values():
        for zone in pl.zones.values():
            if zone.terrain not in models:
                st = stats[zone.terrain]
                models[zone.terrain] = build_model(catalog, zone.terrain, st)
    return models


def grow_level(
    models: Mapping[str, VegModel],
    lv: GrowLevel,
    seed: int,
    sampler: Sampler,
) -> Grown:
    """Grow each zone's vegetation with `sampler` off the taken tiles, the landings and the
    town room, and densify it along the rim outside the entrance bands. A zone whose terrain
    has no vegetation category keeps an empty ``VegetatedZone``."""
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
        zobjs, blocked, _ = sampler.sample(
            ZoneRef(zone.ts, lv.label, zid, lv.centroids[zid], lv.level),
            model,
            seed,
            SampleOptions(
                prot=zone.prot,
                forbid=forbid,
                border=frozenset(zone.rim8 - zone.ent_bands - forbid),
                impassable=zone.town.blk,
                ground=lv.ground,
            ),
        )
        objs.extend(zobjs)
        zones[zid] = VegetatedZone(
            open_set=frozenset(zone.ts - blocked - seaport),
            passable=frozenset(zone.ts - blocked),
        )
    return Grown(tuple(objs), zones)

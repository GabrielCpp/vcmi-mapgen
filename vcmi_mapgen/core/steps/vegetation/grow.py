"""One level's vegetation, grown zone by zone before the border seal."""

from __future__ import annotations

import zlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

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
    the tiles already taken before any tree grows, the level's terrain grid every tree
    must be allowed on, and each zone's patches of another terrain by that terrain's name.
    An empty ``ground`` checks no terrain."""

    level: int
    plan: PlanLevel
    centroids: Mapping[int, tuple[float, float]]
    label: ZoneLabel
    taken: frozenset[Tile]
    ground: Sequence[Sequence[Terrain]] = ()
    patches: Mapping[int, Mapping[str, frozenset[Tile]]] = field(
        default_factory=dict[int, Mapping[str, frozenset[Tile]]]
    )


@dataclass(frozen=True, slots=True)
class Grown:
    """One level's new vegetation in placement order, and each zone's open and passable
    tiles before the seal."""

    objs: tuple[PlacedObject, ...]
    zones: Mapping[int, VegetatedZone]


def vegetation_models(
    catalog: Catalog,
    stats: Mapping[str, VegetationStats],
    plan: ZonePlan,
    patch_terrains: Iterable[str] = (),
) -> dict[str, VegModel]:
    """One fitted model per terrain the plan holds, built from that terrain's ``stats`` in
    the order the zones name them, then one per patch terrain that has statistics."""
    models: dict[str, VegModel] = {}
    for pl in plan.levels.values():
        for zone in pl.zones.values():
            if zone.terrain not in models:
                st = stats[zone.terrain]
                models[zone.terrain] = build_model(catalog, zone.terrain, st)
    for terrain in patch_terrains:
        if terrain not in models and terrain in stats:
            models[terrain] = build_model(catalog, terrain, stats[terrain])
    return models


def ground_patches(
    catalog: Catalog, pl: PlanLevel, ground: Sequence[Sequence[Terrain]]
) -> dict[int, dict[str, frozenset[Tile]]]:
    """Each zone's land tiles whose ground is not the zone's own terrain, grouped by the
    name of the terrain under them."""
    out: dict[int, dict[str, frozenset[Tile]]] = {}
    if not ground:
        return out
    for zid, zone in pl.zones.items():
        by: dict[str, set[Tile]] = {}
        for x, y in zone.ts:
            t = ground[y][x]
            name = catalog.terrain_name(t) if t.is_land else ""
            if name and name != zone.terrain:
                by.setdefault(name, set()).add((x, y))
        if by:
            out[zid] = {name: frozenset(by[name]) for name in sorted(by)}
    return out


def grow_level(
    models: Mapping[str, VegModel],
    lv: GrowLevel,
    seed: int,
    sampler: Sampler,
) -> Grown:
    """Grow each zone's vegetation with `sampler` off the taken tiles, the landings and the
    town room, and densify it along the rim outside the entrance bands. Each patch of another
    terrain then grows with its own terrain's model, walled by what the zone grew. A zone
    whose terrains have no vegetation category keeps an empty ``VegetatedZone``."""
    landings = lv.plan.landings.blk | lv.plan.landings.appr
    objs: list[PlacedObject] = []
    zones: dict[int, VegetatedZone] = {}
    for zid, zone in lv.plan.zones.items():
        ref = ZoneRef(zone.ts, lv.label, zid, lv.centroids[zid], lv.level)
        seaport = landings & zone.ts
        forbid = lv.taken | seaport | zone.town.clear
        blocked: set[Tile] = set()
        grew = False
        runs = [(models[zone.terrain], forbid, seed)]
        for name, tiles in lv.patches.get(zid, {}).items():
            if name in models:
                runs.append(
                    (models[name], forbid | (zone.ts - tiles), seed ^ zlib.crc32(name.encode()))
                )
        for model, run_forbid, run_seed in runs:
            if not model.cats:
                continue
            grew = True
            zobjs, zblocked, _ = sampler.sample(
                ref,
                model,
                run_seed,
                SampleOptions(
                    prot=zone.prot,
                    forbid=run_forbid,
                    border=frozenset(zone.rim8 - zone.ent_bands - run_forbid),
                    impassable=zone.town.blk | blocked,
                    ground=lv.ground,
                ),
            )
            objs.extend(zobjs)
            blocked |= zblocked
        if not grew:
            zones[zid] = VegetatedZone()
            continue
        zones[zid] = VegetatedZone(
            open_set=frozenset(zone.ts - blocked - seaport),
            passable=frozenset(zone.ts - blocked),
        )
    return Grown(tuple(objs), zones)

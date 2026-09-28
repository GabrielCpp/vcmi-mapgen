"""ScatterStep — free resource piles, the last thing placed on the map."""

from __future__ import annotations

import collections
from typing import override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import CoverIndex, MapState, PlacedObject
from vcmi_mapgen.core.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.placement import scatter as SC
from vcmi_mapgen.core.placement.guards import guard_zoc
from vcmi_mapgen.core.placement.rules import TerrainGate
from vcmi_mapgen.core.planning.zone_index import ZoneIndex
from vcmi_mapgen.core.planning.zone_plan import ZonePlan
from vcmi_mapgen.core.steps.gameplay.result import GameplayResult
from vcmi_mapgen.core.steps.terrain_gen.result import Segmentation


class ScatterStep(PipelineStep):
    """Free resource piles over the open field, after every guard, portal rescue, cache and
    loot zone. A pile never sits inside a guard's zone of control, so a free resource beside
    a monster does not look guarded, and it never claims a tile an earlier step used.

    Config:
        seed       RNG seed.
        size       Map side length in tiles (square).

    inject(ctx): ``ZoneIndex`` (zone records), ``Segmentation`` (the zone label grid),
    ``ZonePlan`` (each zone's plan) and ``GameplayResult`` (each zone after placement).

    Produces: appends the piles to ``map_state.objs``.
    """

    def __init__(self, seed: int = 3, size: int = 72) -> None:
        self.seed: int = seed
        self.size: int = size
        self.objs: list[PlacedObject] = []
        self._zones: ZoneIndex = ZoneIndex()
        self._plan: ZonePlan = ZonePlan({}, ())
        self._gameplay: GameplayResult = GameplayResult({}, {}, {})
        self._segmentation: Segmentation = Segmentation({}, {})

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._zones = ctx.require(ZoneIndex)
        self._plan = ctx.require(ZonePlan)
        self._gameplay = ctx.require(GameplayResult)
        self._segmentation = ctx.require(Segmentation)

    @override
    def run(self, catalog: Catalog, map_state: MapState) -> None:
        by_level: dict[int, list[PlacedObject]] = {lvl: [] for lvl in self._zones.zone_records}
        for o in map_state.objs:
            if o.level in by_level:
                by_level[o.level].append(o)

        for level, zone_records in self._zones.zone_records.items():
            level_objs = by_level[level]
            taken = {
                (cx, cy)
                for o in level_objs
                for cx, cy, _b in FP.anchored_cells(o.footprint, o.x, o.y)
            }
            cover = CoverIndex(level_objs, self._zones.claims.get(level, frozenset()) | taken)
            zoc = guard_zoc(level_objs)
            planned = self._plan.levels[level].zones
            placed = self._gameplay.zones[level]
            for zr in zone_records:
                if zr.loot_zone:
                    continue
                zone = planned[zr.zid]
                pz = placed[zr.zid]
                piles, _r = SC.place_scatter(
                    catalog,
                    SC.ScatterZone(
                        zone.ts,
                        self._segmentation.zone_label[level],
                        zr.zid,
                        zone.terrain,
                        pz.open_set - (zone.rim8 - zone.ent_bands),
                        pz.prot,
                        entrances=list(zone.entrances),
                    ),
                    SC.ScatterConfig(
                        seed=self.seed,
                        bounds=(self.size, self.size),
                        cover=cover,
                        reach_in=set(zr.reach),
                        avoid=zoc,
                    ),
                )
                for o in piles:
                    o.level = level
                level_objs.extend(piles)
                self.objs.extend(piles)
                pk = collections.Counter(o.purpose for o in piles)
                print(
                    f"  L{level} zone {zr.zid:>3} {zone.terrain:<8} {len(zone.ts):>5} tiles: "
                    + f"scatter res={pk.get('RESOURCE_PILE', 0)}"
                )

        map_state.add_objs(self.objs, TerrainGate(catalog))

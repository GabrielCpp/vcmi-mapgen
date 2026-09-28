"""ScatterStep — free resource piles, the last thing placed on the map."""

from __future__ import annotations

from typing import override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState, PlacedObject
from vcmi_mapgen.core.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.core.placement.rules import TerrainGate
from vcmi_mapgen.core.planning.zone_index import ZoneIndex
from vcmi_mapgen.core.planning.zone_plan import ZonePlan
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.steps.gameplay.result import GameplayResult
from vcmi_mapgen.core.steps.scatter.piles import PileLevel, scatter_level
from vcmi_mapgen.core.steps.terrain_gen.result import Segmentation


class ScatterStep(PipelineStep):
    """Free resource piles over the open field, after every guard, portal rescue, cache and
    loot zone. A pile never sits inside a guard's zone of control, so a free resource beside
    a monster does not look guarded, and it never claims a tile an earlier step used.

    Config:
        priors     The corpus priors; the step reads the level-0 gameplay statistics.
        seed       RNG seed.
        size       Map side length in tiles (square).

    inject(ctx): ``ZoneIndex`` (zone records), ``Segmentation`` (the zone label grid),
    ``ZonePlan`` (each zone's plan) and ``GameplayResult`` (each zone after placement).

    Produces: appends the piles to ``map_state.objs``.
    """

    def __init__(self, priors: Priors, seed: int = 3, size: int = 72) -> None:
        self.priors: Priors = priors
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
        by_level = map_state.objs_by_level(self._zones.zone_records)
        for level, zone_records in self._zones.zone_records.items():
            lv = PileLevel(
                level,
                zone_records,
                self._plan.levels[level],
                self._gameplay.zones[level],
                self._segmentation.zone_label[level],
                self._zones.claims.get(level, frozenset()),
                self.priors.gameplay[0],
            )
            piles = scatter_level(catalog, lv, by_level[level], self.seed, self.size)
            self.objs.extend(piles.objs)
            for line in piles.log:
                print(line)

        map_state.add_objs(self.objs, TerrainGate(catalog))

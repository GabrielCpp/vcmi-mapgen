"""TreasureStep: fills every sealed loot zone with treasure."""

from __future__ import annotations

from typing import final, override

from vcmi_mapgen.models import MapState, PlacedObject
from vcmi_mapgen.ontology import Ontology
from vcmi_mapgen.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.steps.gated.step import GatedResult
from vcmi_mapgen.steps.treasure.fill import fill_loot_zones
from vcmi_mapgen.steps.zone_index import ZoneIndex
from vcmi_mapgen.validate import TerrainGate


@final
class TreasureStep(PipelineStep):
    """Loot-zone treasure: hero structures, artifacts, chests, scrolls and rare resources on
    the free tiles behind each loot zone's gate or monolith.

    Config:
        seed        RNG seed.
        size        Map side length in tiles (square).

    inject(ctx): ``ZoneIndex`` (zone records, ``used`` mutated in place), ``GatedResult``.

    Produces: appends the treasure to ``map_state.objs``.
    """

    def __init__(self, seed: int = 3, size: int = 72) -> None:
        self.seed = seed
        self.size = size
        self.objs: list[PlacedObject] = []
        self._zones = ZoneIndex()
        self._gated = GatedResult()

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._zones = ctx.require(ZoneIndex)
        self._gated = ctx.require(GatedResult)

    @override
    def run(self, ontology: Ontology, map_state: MapState) -> None:
        for level in self._gated.access:
            level_objs = [o for o in map_state.objs if o.level == level]
            new = self._fill_level(level, level_objs)
            for o in new:
                o.level = level
            self.objs.extend(new)
        map_state.add_objs(self.objs, TerrainGate(ontology))

    def _fill_level(self, level: int, level_objs: list[PlacedObject]) -> list[PlacedObject]:
        footprints = {zid: acc.footprint for zid, acc in self._gated.access[level].items()}
        return fill_loot_zones(
            self._zones.zone_records[level],
            footprints,
            level_objs,
            self.seed,
            (self.size, self.size),
        )

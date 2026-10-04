"""RoadsStep: the roads, laid last, over the tiles every object has left walkable."""

from __future__ import annotations

import random
from dataclasses import replace
from typing import override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.reading.ground import read_ground
from vcmi_mapgen.core.steps.roads.layer import RoadLayer
from vcmi_mapgen.core.steps.roads.sites import map_surface, road_level
from vcmi_mapgen.core.steps.terrain_gen.result import PlaceMap

SALT = 0x40AD


class RoadsStep(PipelineStep):
    """The roads of every level, laid by the ``RoadLayer`` it is given once every object
    stands, so no object covers a road and every road tile stays walkable. Every road of the
    map takes one surface, drawn from the corpus surface counts.

    Config:
        priors  The corpus priors; the step reads each level's road statistics.
        layer   The algorithm that lays one level's roads.
        seed    RNG seed.

    inject(ctx): ``PlaceMap`` (each level's places and passages).

    Produces: ``map_state.roads`` for every level the place map holds.
    """

    def __init__(self, priors: Priors, layer: RoadLayer, seed: int = 3) -> None:
        self.priors: Priors = priors
        self.layer: RoadLayer = layer
        self.seed: int = seed
        self._places: PlaceMap = PlaceMap({})

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._places = ctx.require(PlaceMap)

    @override
    def run(self, catalog: Catalog, map_state: MapState) -> None:
        stats_by_level = self.priors.places.values()
        surface = map_surface((s.roads for s in stats_by_level), random.Random(self.seed ^ SALT))
        for level, places in sorted(self._places.levels.items()):
            ground = read_ground(catalog, map_state, level)
            stats = self.priors.places.get(level)
            if ground is None or stats is None:
                continue
            lv = replace(road_level(catalog, ground, places, map_state, level), surface=surface)
            map_state.roads[level] = dict(self.layer.lay(stats.roads, lv))

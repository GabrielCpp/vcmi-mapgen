"""TerrainStep: one ``Terrain`` grid per level and the place map under it, drawn by the
``TerrainModel`` it is given, then segmented into one zone per place. Tile art is the
export's job, so no frame or flip leaves this step."""

from __future__ import annotations

from typing import override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.steps.terrain_gen.levels import level_accents, segment_places
from vcmi_mapgen.core.steps.terrain_gen.model import TerrainModel, TerrainOptions
from vcmi_mapgen.core.steps.terrain_gen.result import TerrainGrids


class TerrainStep(PipelineStep):
    """Draw each level's terrain and place map, and segment the places into zones.

    Config:
        priors   The corpus priors; the model reads the terrain and place statistics.
        model    The ``TerrainModel`` that draws the grids and the place map.
        seed     RNG seed.
        options  Map side, water mode, underground and player count.

    Produces: ``map_state.terrain``; ``TerrainGrids``, the tunnel cells despeckle kept;
    ``PlaceMap``, each level's places; ``Segmentation``, each level's zones, one per place,
    and zone label grid; ``Accents``, each level's accent patches.
    """

    def __init__(
        self, priors: Priors, model: TerrainModel, seed: int, options: TerrainOptions
    ) -> None:
        self.priors: Priors = priors
        self.model: TerrainModel = model
        self.seed: int = seed
        self.options: TerrainOptions = options
        self._ctx: ProviderRegistry | None = None

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx

    @override
    def run(self, catalog: Catalog, map_state: MapState) -> None:
        if self._ctx is None:
            raise RuntimeError("TerrainStep.run() requires inject() to have been called")
        draw = self.model.draw(catalog, self.priors, self.seed, self.options)
        for line in draw.log:
            print(line)
        map_state.terrain = dict(draw.grids)
        self._ctx.provide(TerrainGrids(tunnel_protect=draw.tunnel_protect))
        self._ctx.provide(draw.places)
        segmentation, warnings = segment_places(map_state.terrain, draw.places, draw.tunnel_protect)
        for line in warnings:
            print(line)
        self._ctx.provide(segmentation)
        self._ctx.provide(level_accents(map_state.terrain, draw.places))

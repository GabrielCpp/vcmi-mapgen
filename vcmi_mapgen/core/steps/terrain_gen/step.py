"""TerrainStep: macro terrain for the surface and the underground, despeckled into one
``Terrain`` grid per level, then segmented into same-terrain zones. Tile art is the
export's job, so no frame or flip leaves this step."""

from __future__ import annotations

from typing import override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState, Tile
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.core.steps.terrain_gen import macro as MTOPO
from vcmi_mapgen.core.steps.terrain_gen.despeckle import despeckle
from vcmi_mapgen.core.steps.terrain_gen.levels import level_protect, raw_levels, segment_levels
from vcmi_mapgen.core.steps.terrain_gen.result import TerrainGrids


class TerrainStep(PipelineStep):
    """Generate macro terrain and despeckle it into the level's ``Terrain`` grid.

    Config:
        size        Map side length in tiles (square).
        seed        RNG seed.
        water       Explicit water fraction override (None = corpus-drawn).
        water_mode  'none' | 'normal' | 'islands'
        subterrain  Whether to generate a second underground level.

    Produces: ``map_state.terrain``; ``TerrainGrids``, the tunnel cells despeckle kept;
    ``Segmentation``, each level's same-terrain zones and zone label grid.
    """

    def __init__(
        self,
        size: int = 72,
        seed: int = 3,
        water: float | None = None,
        water_mode: str = "normal",
        subterrain: bool = False,
    ) -> None:
        self.size: int = size
        self.seed: int = seed
        self.water: float | None = water
        self.water_mode: str = water_mode
        self.subterrain: bool = subterrain
        self.terrain: dict[int, list[list[Terrain]]] = {}
        self.tunnel_protect: frozenset[Tile] = frozenset()
        self._ctx: ProviderRegistry | None = None

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx

    @override
    def run(self, catalog: Catalog, map_state: MapState) -> None:
        raw = raw_levels(
            self.size,
            self.seed,
            MTOPO.MacroOptions(water=self.water, water_mode=self.water_mode, level=0),
            self.subterrain,
        )
        thin = catalog.thin_terrains()
        for level, grid in raw.grids.items():
            self.terrain[level] = despeckle(grid, thin, level_protect(level, raw.tunnel_protect))
        self.tunnel_protect = raw.tunnel_protect
        map_state.terrain = self.terrain
        if self._ctx is None:
            raise RuntimeError("TerrainStep.run() requires inject() to have been called")
        self._ctx.provide(TerrainGrids(tunnel_protect=self.tunnel_protect))
        segmentation, warnings = segment_levels(self.terrain, self.tunnel_protect)
        for line in warnings:
            print(line)
        self._ctx.provide(segmentation)

"""TerrainStep: macro terrain for the surface and the underground, despeckled into one
``Terrain`` grid per level, then segmented into same-terrain zones. Tile art is the
export's job, so no frame or flip leaves this step."""

from __future__ import annotations

from collections.abc import Mapping
from typing import override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.segment import ZoneLabel, segment_level
from vcmi_mapgen.core.model import MapState, Tile, Zone
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.core.steps.terrain_gen import macro as MTOPO
from vcmi_mapgen.core.steps.terrain_gen.despeckle import despeckle
from vcmi_mapgen.core.steps.terrain_gen.gate_sites import carve_gate_sites, gate_anchor_points
from vcmi_mapgen.core.steps.terrain_gen.result import Segmentation, TerrainGrids


def _warn_sliver_zones(
    zones: Mapping[int, Zone], level: int, protect: frozenset[Tile] | None = None
) -> None:
    min_area = 25
    guard: frozenset[Tile] = frozenset() if protect is None else protect
    for zid, z in zones.items():
        if z.area < min_area and not (z.tiles_set & guard):
            print(
                f"  WARNING: level {level} zone {zid} is very small ({z.area} tiles, "
                + f"terrain {z.terrain_type})"
            )


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
        W = H = self.size

        grid0 = MTOPO.generate(
            W,
            H,
            seed=self.seed,
            options=MTOPO.MacroOptions(water=self.water, water_mode=self.water_mode, level=0),
        )

        tunnel_protect_cells: set[Tile] = set()
        grid1: list[list[int]] | None = None
        if self.subterrain:
            grid1 = MTOPO.generate(
                W,
                H,
                seed=self.seed ^ 0x51E9,
                options=MTOPO.MacroOptions(level=1),
                protect_out=tunnel_protect_cells,
            )
            gate_anchors = gate_anchor_points(W, H, self.seed)
            tunnel_protect_cells |= carve_gate_sites(grid0, grid1, gate_anchors, self.seed)
        tunnel_protect = frozenset(tunnel_protect_cells)

        raw_grids = {0: grid0}
        if grid1 is not None:
            raw_grids[1] = grid1

        thin = catalog.thin_terrains()
        for level, grid in raw_grids.items():
            protect: frozenset[Tile] = tunnel_protect if level == 1 else frozenset()
            self.terrain[level] = despeckle(grid, thin, protect)

        self.tunnel_protect = tunnel_protect
        map_state.terrain = self.terrain
        if self._ctx is None:
            raise RuntimeError("TerrainStep.run() requires inject() to have been called")
        self._ctx.provide(TerrainGrids(tunnel_protect=self.tunnel_protect))
        zones: dict[int, dict[int, Zone]] = {}
        labels: dict[int, ZoneLabel] = {}
        for level, grid in self.terrain.items():
            zones[level], labels[level], _ = segment_level(grid)
            protect = tunnel_protect if level == 1 else frozenset()
            _warn_sliver_zones(zones[level], level, protect=protect)
        self._ctx.provide(Segmentation(zones, labels))

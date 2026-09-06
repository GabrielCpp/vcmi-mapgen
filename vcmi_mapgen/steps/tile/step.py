"""TileStep — corpus-learned autotiling: despeckle + H3-correct transition views."""
from __future__ import annotations

from vcmi_mapgen.pipeline import PipelineStep
from vcmi_mapgen.kit import tiling as TL
from vcmi_mapgen.kit import vmap as VM


class TileStep(PipelineStep):
    """Apply corpus-learned terrain autotiling to every active level.

    Config:
        size  Map side length in tiles (square) — matches TerrainGenStep's.

    inject(ctx): ``grids``, ``tunnel_protect`` (TerrainGenStep's ctx output).

    Produces:
      - ``cells``, ``surfs``  — written directly onto MapState.
      - ``grids``  — post-despeckle terrain-code grids, written back into ctx
        (consumed by GameplayStep/RepairStep — supersedes TerrainGenStep's raw grids).
    """

    def __init__(self, size: int = 72) -> None:
        self.size = size
        self.cells: dict = {}
        self.surfs: dict = {}
        self.grids: dict = {}
        self._ctx: dict = {}
        self._input_grids: dict = {}
        self._tunnel_protect: frozenset = frozenset()

    def inject(self, ctx: dict) -> None:
        self._ctx = ctx
        self._input_grids = self._require(ctx, "grids", dict)
        self._tunnel_protect = frozenset(
            self._require(ctx, "tunnel_protect", (set, frozenset)))

    def run(self, ontology, map_state) -> None:
        W = H = self.size
        protect = self._tunnel_protect

        for level, grid in self._input_grids.items():
            kw = {"protect": protect} if level == 1 else {}
            cells = TL.tile_terrain(grid, W, H, **kw)
            self.cells[level] = cells
            self.surfs[level] = [[VM.tile_string(c) for c in row] for row in cells]
            # post-despeckle terrain codes, for steps that need the terrain grid itself
            self.grids[level] = [[c["t"] for c in row] for row in cells]

        map_state.cells = self.cells
        map_state.surfs = self.surfs
        self._ctx["grids"] = self.grids

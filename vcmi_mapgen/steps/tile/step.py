"""TileStep — corpus-learned autotiling: despeckle + H3-correct transition views."""
from __future__ import annotations

from vcmi_mapgen.pipeline import PipelineStep
from vcmi_mapgen.kit import tiling as TL
from vcmi_mapgen.kit import vmap as VM


class TileStep(PipelineStep):
    """Apply corpus-learned terrain autotiling to every active level.

    Config:
        size  Map side length in tiles (square) — matches TerrainGenStep's.

    inject(grids, tunnel_protect): ``grids`` (TerrainGenStep's output) and
    ``tunnel_protect`` (TerrainGenStep's output).

    Produces:
      - ``cells``  — 2-D tile-dict grids (t, view, rt, …)
      - ``surfs``  — 2-D tile-string grids (e.g. "gr2_")
      - ``grids``  — post-despeckle terrain-code grids (consumed by GameplayStep/RepairStep)
    """

    def __init__(self, size: int = 72) -> None:
        self.size = size
        self.cells: dict = {}
        self.surfs: dict = {}
        self.grids: dict = {}
        self._input_grids: dict = {}
        self._tunnel_protect: frozenset = frozenset()

    def inject(self, *, grids: dict, tunnel_protect) -> None:
        self._input_grids = grids
        self._tunnel_protect = frozenset(tunnel_protect)

    def run(self) -> None:
        W = H = self.size
        protect = self._tunnel_protect

        for level, grid in self._input_grids.items():
            kw = {"protect": protect} if level == 1 else {}
            cells = TL.tile_terrain(grid, W, H, **kw)
            self.cells[level] = cells
            self.surfs[level] = [[VM.tile_string(c) for c in row] for row in cells]
            # post-despeckle terrain codes, for steps that need the terrain grid itself
            self.grids[level] = [[c["t"] for c in row] for row in cells]

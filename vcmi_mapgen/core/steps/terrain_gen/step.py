"""TerrainStep — macro terrain generation + corpus-learned autotiling for surface and
underground levels, in one step.

Merge of the former TerrainGenStep + TileStep: TileStep's autotiling was the sole
consumer of TerrainGenStep's raw macro grid, run immediately next and superseding it —
an artificial two-step handoff for what is really one step's job (see
vcmi_mapgen/core/steps/AGENTS.md). The raw pre-tile grid is now a private intermediate that
never leaves this step; only the post-despeckle terrain-code grids (needed downstream by
VegetationStep/GameplayStep/BorderStep) and tunnel_protect are published, as one
TerrainGrids value. The step then segments each level into same-terrain zones and
publishes them as Segmentation."""

from __future__ import annotations

import collections
import math
import random
from collections.abc import Mapping
from dataclasses import dataclass
from typing import override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.segment import ZoneLabel, segment_level
from vcmi_mapgen.core.model import Cell, MapState, Tile, Zone
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.core.steps.terrain_gen import macro_topo as MTOPO
from vcmi_mapgen.core.steps.terrain_gen.result import Segmentation, TerrainGrids
from vcmi_mapgen.kit import tiling as TL
from vcmi_mapgen.vcmi.formats import vmap as VM


@dataclass(frozen=True, slots=True)
class _GateLayout:
    n_sites: int = 8
    margin: int = 8
    pad: int = 4


def _gate_anchor_points(W: int, H: int, seed: int, layout: _GateLayout | None = None) -> list[Tile]:
    lay = _GateLayout() if layout is None else layout
    n_sites, margin, pad = lay.n_sites, lay.margin, lay.pad
    rng = random.Random(seed ^ 0xA7E5)
    cols = max(1, round(math.pow(n_sites, 0.5)))
    rows = -(-n_sites // cols)
    lo, hi_x, hi_y = margin, W - margin, H - margin
    anchors: list[Tile] = []
    for i in range(n_sites):
        gx = lo + (hi_x - lo) * ((i % cols) + 0.5) / cols
        gy = lo + (hi_y - lo) * ((i // cols) + 0.5) / rows
        ax = min(W - 2 - pad, max(margin, int(gx) + rng.randint(-3, 3)))
        ay = min(H - 3 - pad, max(margin, int(gy) + rng.randint(-3, 3)))
        anchors.append((ax, ay))
    return anchors


def _gate_site_cells(ax: int, ay: int, pad: int = 4) -> set[Tile]:
    r2 = (pad + 0.5) ** 2
    return {
        (ax + dx, ay + dy)
        for dy in range(-pad, pad + 1)
        for dx in range(-pad, pad + 1)
        if dx * dx + dy * dy <= r2
    }


def _carve_gate_sites(
    grid0: list[list[int]],
    grid1: list[list[int]] | None,
    anchors: list[Tile],
    seed: int,
    pad: int = 4,
) -> set[Tile]:
    H = len(grid0)
    W = len(grid0[0])
    land0 = collections.Counter(
        grid0[y][x] for y in range(H) for x in range(W) if grid0[y][x] != Terrain.WATER
    )
    fill0 = land0.most_common(1)[0][0] if land0 else 2
    protect1: set[Tile] = set()
    if grid1 is None:
        for ax, ay in anchors:
            for x, y in _gate_site_cells(ax, ay, pad):
                if 0 <= x < W and 0 <= y < H:
                    grid0[y][x] = fill0
        return protect1

    land1 = collections.Counter(
        grid1[y][x] for y in range(H) for x in range(W) if Terrain(grid1[y][x]).is_land
    )
    fill1 = land1.most_common(1)[0][0] if land1 else 6
    land1_before = {(x, y) for y in range(H) for x in range(W) if Terrain(grid1[y][x]).is_land}
    rng = random.Random(seed ^ 0xC0DE)
    for ax, ay in anchors:
        for x, y in _gate_site_cells(ax, ay, pad):
            if 0 <= x < W and 0 <= y < H:
                grid0[y][x] = fill0
                grid1[y][x] = fill1
        if land1_before:
            tx, ty = min(land1_before, key=lambda t: (t[0] - ax) ** 2 + (t[1] - ay) ** 2)
            _tunnel_underground(grid1, ((ax, ay), (tx, ty)), fill1, rng, protect1)
        land1_before.add((ax, ay))
    return protect1


def _tunnel_underground(
    grid1: list[list[int]],
    span: tuple[Tile, Tile],
    fill1: int,
    rng: random.Random,
    protect1: set[Tile],
) -> None:
    H = len(grid1)
    W = len(grid1[0])
    land_bool = [[Terrain(grid1[y][x]).is_land for x in range(W)] for y in range(H)]
    MTOPO.carve_corridor(land_bool, span, rng, half_w=1, protect=protect1)
    for y in range(H):
        for x in range(W):
            if land_bool[y][x] and Terrain(grid1[y][x]).is_barrier:
                grid1[y][x] = fill1


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
    """Generate macro terrain, then apply corpus-learned autotiling — both passes owned
    by one step so the raw pre-tile grid never has to leave it as its own cross-step
    value (see the module docstring for why the old two-step split was an artificial
    handoff).

    Config:
        size        Map side length in tiles (square).
        seed        RNG seed.
        water       Explicit water fraction override (None = corpus-drawn).
        water_mode  'none' | 'normal' | 'islands'
        subterrain  Whether to generate a second underground level.

    Produces: ``map_state.cells``/``surfs`` (the finished, VCMI-tile-string terrain);
    ``TerrainGrids`` (post-despeckle terrain-code grids + tunnel_protect), for
    VegetationStep/GameplayStep/BorderStep; ``Segmentation``, each level's same-terrain
    zones and zone label grid.
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
        self.cells: dict[int, list[list[Cell]]] = {}
        self.surfs: dict[int, list[list[str]]] = {}
        self.grids: dict[int, list[list[int]]] = {}
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
            gate_anchors = _gate_anchor_points(W, H, self.seed)
            tunnel_protect_cells |= _carve_gate_sites(grid0, grid1, gate_anchors, self.seed)
        tunnel_protect = frozenset(tunnel_protect_cells)

        raw_grids = {0: grid0}
        if grid1 is not None:
            raw_grids[1] = grid1

        for level, grid in raw_grids.items():
            protect: frozenset[Tile] = tunnel_protect if level == 1 else frozenset()
            cells = TL.tile_terrain(grid, W, H, protect)
            self.cells[level] = cells
            self.surfs[level] = [[VM.tile_string(c) for c in row] for row in cells]
            # post-despeckle terrain codes, for steps that need the terrain grid itself
            self.grids[level] = [[c.t for c in row] for row in cells]

        self.tunnel_protect = tunnel_protect
        map_state.cells = self.cells
        map_state.surfs = self.surfs
        if self._ctx is None:
            raise RuntimeError("TerrainStep.run() requires inject() to have been called")
        self._ctx.provide(TerrainGrids(grids=self.grids, tunnel_protect=self.tunnel_protect))
        zones: dict[int, dict[int, Zone]] = {}
        labels: dict[int, ZoneLabel] = {}
        for level, cells in self.cells.items():
            zones[level], labels[level], _ = segment_level(cells)
            protect = tunnel_protect if level == 1 else frozenset()
            _warn_sliver_zones(zones[level], level, protect=protect)
        self._ctx.provide(Segmentation(zones, labels))

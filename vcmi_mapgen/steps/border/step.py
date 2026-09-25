"""BorderStep: closes every zone border outside the planned entrances."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import final, override

from vcmi_mapgen.models import MapState, PlacedObject, Tile, ZoneRecord
from vcmi_mapgen.ontology import Ontology
from vcmi_mapgen.pipeline import PipelineStep, PlacementWorkspace, ProviderRegistry
from vcmi_mapgen.steps.border import border_seal as BS
from vcmi_mapgen.steps.pickup.step import PickupIndex
from vcmi_mapgen.steps.terrain_gen.step import TerrainGrids
from vcmi_mapgen.validate import TerrainGate


@dataclass
class BorderResult:
    """Diagnostic log lines for the CLI to print."""

    log: list[str] = field(default_factory=list)


@final
class BorderStep(PipelineStep):
    """Residual border-leak seal: single blocking decorations on open cross-zone pairs, a
    guard where a crossing must stay open.

    Config:
        seed        RNG seed.
        size        Map side length in tiles (square).

    inject(ctx): ``PickupIndex`` (zone records), ``TerrainGrids``, the shared
    ``PlacementWorkspace`` (``entrance_plan``/``seal_avoid``/``hard_avoid``; writes
    ``guard_tiles`` back per level).

    Produces: replaces ``map_state.objs`` and provides ``BorderResult``.
    """

    def __init__(self, seed: int = 3, size: int = 72) -> None:
        self.seed = seed
        self.size = size
        self.objs: list[PlacedObject] = []
        self.log: list[str] = []
        self._ctx = ProviderRegistry()
        self._zone_records: dict[int, list[ZoneRecord]] = {}
        self._grids: dict[int, list[list[int]]] = {}
        self._workspace = PlacementWorkspace()

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx
        self._zone_records = ctx.require(PickupIndex).zone_records
        self._grids = ctx.require(TerrainGrids).grids
        self._workspace = ctx.require(PlacementWorkspace)

    @override
    def run(self, ontology: Ontology, map_state: MapState) -> None:
        W = H = self.size
        objs_by_level: dict[int, list[PlacedObject]] = {lvl: [] for lvl in self._grids}
        for o in map_state.objs:
            if o.level in objs_by_level:
                objs_by_level[o.level].append(o)

        for level in sorted(self._grids):
            lvl_ws = self._workspace.levels[level]
            zone_records = self._zone_records[level]
            loot_ts: set[Tile] = set()
            for zr in zone_records:
                if zr.loot_zone:
                    loot_ts |= zr.ts
            bands: set[Tile] = set()
            for ents in lvl_ws.entrance_plan.values():
                for _r, b, _o in ents:
                    bands |= b
            new_objs, guard_tiles, n_open = BS.guard_crossings(
                W,
                H,
                self._grids[level],
                map_state.zones[level],
                bands,
                objs_by_level[level],
                lvl_ws.hard_avoid,
                self.seed,
                level,
                skip_tiles=loot_ts,
            )
            if level == 1:
                for o in new_objs:
                    o.level = 1
            objs_by_level[level].extend(new_objs)
            if guard_tiles or n_open:
                self.log.append(
                    f"L{level} border guards: {len(guard_tiles)}"
                    + (f", {n_open} crossings left free (unguardable)" if n_open else "")
                )
            for zr in zone_records:
                zr.open_set -= guard_tiles
            lvl_ws.guard_tiles = frozenset(guard_tiles)

        self.objs = [o for lvl in sorted(objs_by_level) for o in objs_by_level[lvl]]
        map_state.set_objs(self.objs, TerrainGate(ontology))
        self._ctx.provide(BorderResult(log=self.log))

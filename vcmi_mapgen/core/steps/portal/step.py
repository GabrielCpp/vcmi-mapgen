"""PortalStep: links every cut-off zone to the start zone with a portal pair."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import final, override

from vcmi_mapgen.core.model import MapState, PlacedObject, Tile, Zone, ZoneRecord
from vcmi_mapgen.core.pipeline import PipelineStep, PlacementWorkspace, ProviderRegistry
from vcmi_mapgen.core.steps.gameplay.gate_pairs import GateResult
from vcmi_mapgen.core.steps.gameplay.step import TownsIndex
from vcmi_mapgen.core.steps.portal import geometry as GEO
from vcmi_mapgen.core.steps.terrain_gen.step import TerrainGrids
from vcmi_mapgen.core.steps.zone_index import ZoneIndex
from vcmi_mapgen.kit.terrain_lookup import TNAME
from vcmi_mapgen.validate import TerrainGate
from vcmi_mapgen.vcmi.catalog.adapter import Ontology


@dataclass
class PortalResult:
    """Diagnostic log lines for the CLI to print."""

    log: list[str] = field(default_factory=list)


def _find_start(
    player_zids: Sequence[tuple[int, int]],
    zones_by_level: Mapping[int, Mapping[int, Zone]],
    workspace: PlacementWorkspace,
) -> tuple[int, Tile] | None:
    """Return (level, (x, y)) for the first player town, or centroid of the
    largest surface land zone when there are no players."""
    for lvl, zid in player_zids:
        lvl_ws = workspace.levels.get(lvl)
        t = lvl_ws.town_of_zone.get(zid) if lvl_ws is not None else None
        if t is not None:
            return (lvl, (t.x, t.y))
    zones0 = zones_by_level.get(0, {})
    big = max(
        (z for z in zones0.values() if TNAME.get(z.terrain_type) not in (None, "water", "rock")),
        key=lambda z: z.area,
        default=None,
    )
    if big is not None:
        bx, by = big.centroid
        return (0, min(big.tiles_set, key=lambda t: ((t[0] - bx) ** 2 + (t[1] - by) ** 2, t)))
    return None


@final
class PortalStep(PipelineStep):
    """Portal rescue: a zone the start cannot walk to gets a portal pair.

    Config:
        seed        RNG seed.
        size        Map side length in tiles (square).

    inject(ctx): ``ZoneIndex`` (targets/zone_records, mutated in place), ``TerrainGrids``,
    ``TownsIndex`` (player_zids), the shared ``PlacementWorkspace``; ``GateResult``
    defaults to empty when GameplayStep has not run.

    Produces: appends the portals and their guards to ``map_state.objs`` and provides
    ``PortalResult``.
    """

    def __init__(self, seed: int = 3, size: int = 72) -> None:
        self.seed = seed
        self.size = size
        self.objs: list[PlacedObject] = []
        self.log: list[str] = []
        self._ctx = ProviderRegistry()
        self._targets: dict[int, list[Tile]] = {}
        self._zone_records: dict[int, list[ZoneRecord]] = {}
        self._grids: dict[int, list[list[int]]] = {}
        self._workspace = PlacementWorkspace()
        self._player_zids: list[tuple[int, int]] = []
        self._gate_objs: list[PlacedObject] = []

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx
        zones = ctx.require(ZoneIndex)
        self._targets = zones.targets
        self._zone_records = zones.zone_records
        self._grids = ctx.require(TerrainGrids).grids
        self._workspace = ctx.require(PlacementWorkspace)
        self._player_zids = ctx.require(TownsIndex).player_zids
        self._gate_objs = ctx.get(GateResult, GateResult()).gate_objs

    @override
    def run(self, ontology: Ontology, map_state: MapState) -> None:
        grids = self._grids
        objs_by_level: dict[int, list[PlacedObject]] = {lvl: [] for lvl in grids}
        for o in map_state.objs:
            if o.level in objs_by_level:
                objs_by_level[o.level].append(o)

        gate_xy = {(o.x, o.y) for o in self._gate_objs if o.level == 0}
        start = _find_start(self._player_zids, map_state.zones, self._workspace)
        if start is not None:
            n_portals = GEO.rescue_unreachable_zones(
                GEO.PortalWorld(
                    self.size,
                    grids,
                    map_state.zones,
                    objs_by_level,
                    self._targets,
                    self._zone_records,
                ),
                start,
                gate_xy,
                self.seed,
            )
            if n_portals:
                self.log.append(f"PortalStep: {n_portals} portal rescue(s) added")

        for level in sorted(grids):
            cut = GEO.unreachable_targets(
                self.size, grids[level], objs_by_level[level], self._targets[level]
            )
            if cut:
                raise ValueError(
                    f"PortalStep: L{level} has {len(cut)} target(s) cut off on foot, first {cut[0]}"
                )

        for o in objs_by_level.get(1, []):
            o.level = 1
        before = {id(o) for o in map_state.objs}
        self.objs = [
            o for lvl in sorted(objs_by_level) for o in objs_by_level[lvl] if id(o) not in before
        ]
        map_state.add_objs(self.objs, TerrainGate(ontology))
        self._ctx.provide(PortalResult(log=self.log))

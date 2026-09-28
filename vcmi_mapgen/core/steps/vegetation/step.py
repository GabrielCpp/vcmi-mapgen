"""VegetationStep — place terrain-matched decorative vegetation per zone."""

from __future__ import annotations

from typing import override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.components import open_islands
from vcmi_mapgen.core.model import MapState, PlacedObject, Tile
from vcmi_mapgen.core.model.map_state import index_of
from vcmi_mapgen.core.pipeline import (
    LevelWorkspace,
    PipelineStep,
    PlacementWorkspace,
    ProviderRegistry,
)
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.placement.rules import TerrainGate
from vcmi_mapgen.core.planning import zone_plan as ZPL
from vcmi_mapgen.core.steps.terrain_gen.result import Segmentation, TerrainGrids
from vcmi_mapgen.core.steps.vegetation import sample as PP
from vcmi_mapgen.core.steps.vegetation.border_plan import BorderPlan, seal_borders
from vcmi_mapgen.core.steps.vegetation.result import VegetationResult


def _check_islands(map_state: MapState, level: int, lvl_ws: LevelWorkspace) -> None:
    land: set[Tile] = set()
    anchors: set[Tile] = set(lvl_ws.seaport_blk | lvl_ws.seaport_appr)
    for zw in lvl_ws.zones.values():
        land |= zw.ts_full
        anchors |= zw.prot | set(zw.approaches)
    blocking = {
        (cx, cy)
        for o in map_state.objs
        if o.level == level
        for cx, cy, blk in FP.anchored_cells(o.footprint, o.x, o.y)
        if blk
    }
    islands = open_islands(land, blocking, anchors)
    if islands:
        first = min(min(c) for c in islands)
        raise ValueError(
            f"VegetationStep: L{level} has {len(islands)} walled-off pocket(s) at {first}"
        )


def _taken(map_state: MapState, level: int, lvl_ws: LevelWorkspace) -> frozenset[Tile]:
    sea = frozenset(t for lvl, t in index_of(list(lvl_ws.sea)) if lvl == level)
    return map_state.taken_tiles(level) | sea


class VegetationStep(PipelineStep):
    """Corpus-fitted Gibbs marked-point-process vegetation, per zone.

    Config:
        seed     RNG seed.
        players  Number of player zones whose town spot stays clear of trees.

    inject(ctx): ``TerrainGrids`` (the tunnel cells), ``Segmentation`` (TerrainStep's zones) and the
    ``PlacementWorkspace``, created here and filled by ``zone_plan.plan_zones`` and
    ``zone_plan.plan_player_zones`` before any tree grows; each zone's ``ZoneWorkspace`` supplies
    ``prot``/``occupied``/``gblocked``/``approaches``/
    ``gobjs``/``rim8``/``ent_bands``/``town_clear``/``town_blk``, and this step writes
    ``blocked``/``open_set``/``passable`` back into the same object for GatedStep.

    Produces: extends ``map_state.objs`` with this step's own new vegetation objects
    (``self.objs`` keeps just the new ones, for callers that want that distinction).
    """

    def __init__(self, seed: int = 3, players: int = 0) -> None:
        self.seed: int = seed
        self.players: int = players
        self.objs: list[PlacedObject] = []
        self.log: list[str] = []
        self._ctx: ProviderRegistry = ProviderRegistry()
        self._workspace: PlacementWorkspace | None = None
        self._terrain: TerrainGrids = TerrainGrids()
        self._segmentation: Segmentation = Segmentation({}, {})
        self._tunnel_protect: frozenset[Tile] = frozenset()

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx
        self._workspace = ctx.get_or_create(PlacementWorkspace, PlacementWorkspace)
        self._terrain = ctx.require(TerrainGrids)
        self._segmentation = ctx.require(Segmentation)
        self._tunnel_protect = self._terrain.tunnel_protect

    @override
    def run(self, catalog: Catalog, map_state: MapState) -> None:
        if self._workspace is None:
            raise RuntimeError("VegetationStep.run() requires inject() to have been called")
        terrain = ZPL.PlanTerrain(
            self._segmentation, map_state.terrain, self._terrain.tunnel_protect
        )
        ZPL.plan_zones(catalog, self._workspace, terrain, self.seed)
        ZPL.plan_player_zones(
            catalog,
            self._workspace,
            self._segmentation.zones,
            self._terrain.tunnel_protect,
            self.players,
        )
        models: dict[str, PP.VegModel] = {}
        new_objs: list[PlacedObject] = []
        pre_taken = {lvl: _taken(map_state, lvl, lw) for lvl, lw in self._workspace.levels.items()}

        for level, lvl_ws in self._workspace.levels.items():
            for zid, zw in lvl_ws.zones.items():
                zones = self._segmentation.zones[level]
                terrain = zw.terrain
                ts = zw.ts
                ts_full = zw.ts_full

                if terrain not in models:
                    models[terrain] = PP.build_model(catalog, terrain)
                model = models[terrain]
                if not model.cats:
                    continue

                # Seaport footprint in this zone must be excluded from vegetation
                zone_seaport_cells = (lvl_ws.seaport_blk | lvl_ws.seaport_appr) & ts_full
                forbid = (
                    _taken(map_state, level, lvl_ws)
                    | zone_seaport_cells
                    | zw.occupied
                    | zw.town_clear
                )
                # zone-isolation border belt: the whole 8-connected rim minus the planned
                # entrance bands (those sit in `prot` as hard zeros) gets the +BORDER_W
                # vegetation bias — both zones densify their own side, so the border reads
                # as a ~2-thick ridge.
                border = frozenset(zw.rim8 - zw.ent_bands - forbid)
                zobjs, blocked, _ = PP.sample_zone(
                    PP.ZoneRef(ts, self._segmentation.zone_label[level], zid, zones[zid].centroid),
                    model,
                    seed=self.seed,
                    opts=PP.SampleOptions(
                        prot=zw.prot,
                        forbid=forbid,
                        border=border,
                        impassable=zw.gblocked | zw.town_blk,
                    ),
                )
                if level == 1:  # sample_zone always tags l=0; retag the underground level
                    for o in zobjs:
                        o.level = 1
                new_objs.extend(zobjs)

                open_set = (
                    ts
                    - blocked
                    - zw.gblocked
                    - set(zw.occupied)
                    - set(zw.approaches)
                    - zone_seaport_cells
                )
                passable = ts - blocked - zw.gblocked

                zw.blocked = frozenset(blocked)
                zw.open_set = frozenset(open_set)
                zw.passable = frozenset(passable)

        self.objs = new_objs
        map_state.add_objs(new_objs, TerrainGate(catalog))
        for level, lvl_ws in self._workspace.levels.items():
            self._seal_level(catalog, map_state, level, lvl_ws, pre_taken[level])
        for level, lvl_ws in self._workspace.levels.items():
            _check_islands(map_state, level, lvl_ws)
        self._ctx.provide(VegetationResult(log=self.log))

    def _seal_level(
        self,
        catalog: Catalog,
        map_state: MapState,
        level: int,
        lvl_ws: LevelWorkspace,
        taken: frozenset[Tile],
    ) -> None:
        land: set[Tile] = set()
        bands: set[Tile] = set()
        avoid: set[Tile] = set(lvl_ws.seaport_blk | lvl_ws.seaport_appr)
        web: set[Tile] = set()
        avoid |= taken
        if level == 1:
            avoid |= self._tunnel_protect
        for zw in lvl_ws.zones.values():
            land |= zw.ts_full
            bands |= zw.ent_bands
            web |= zw.prot
            avoid |= set(zw.approaches) | zw.occupied | zw.town_clear
        level_objs = [o for o in [*lvl_ws.sea, *map_state.objs] if o.level == level]
        sealers, sealed = seal_borders(
            catalog,
            BorderPlan(land, self._segmentation.zones[level], bands, avoid, web),
            level_objs,
            self.seed,
            level,
        )
        if not sealers:
            return
        if level == 1:
            for o in sealers:
                o.level = 1
        self.objs.extend(sealers)
        map_state.add_objs(sealers, TerrainGate(catalog))
        for zw in lvl_ws.zones.values():
            mine = sealed & zw.ts_full
            zw.blocked |= mine
            zw.open_set -= mine
            zw.passable -= mine
        self.log.append(f"L{level} border plan: {len(sealed)} cells closed")

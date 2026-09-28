"""VegetationStep — place terrain-matched decorative vegetation per zone."""

from __future__ import annotations

from typing import override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.components import open_islands
from vcmi_mapgen.core.model import MapState, PlacedObject, Tile
from vcmi_mapgen.core.model.map_state import index_of
from vcmi_mapgen.core.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.placement.rules import TerrainGate
from vcmi_mapgen.core.planning import zone_plan as ZPL
from vcmi_mapgen.core.steps.terrain_gen.result import Segmentation, TerrainGrids
from vcmi_mapgen.core.steps.vegetation.border_plan import BorderPlan, seal_borders
from vcmi_mapgen.core.steps.vegetation.grow import GrowLevel, grow_level, vegetation_models
from vcmi_mapgen.core.steps.vegetation.result import VegetatedZone, VegetationResult

NO_TILES: frozenset[Tile] = frozenset()


def _check_islands(map_state: MapState, level: int, pl: ZPL.PlanLevel) -> None:
    land: set[Tile] = set()
    anchors: set[Tile] = set(pl.landings.blk | pl.landings.appr)
    for zone in pl.zones.values():
        land |= zone.ts
        anchors |= zone.prot
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


def _taken(map_state: MapState, level: int, pl: ZPL.PlanLevel) -> frozenset[Tile]:
    sea = frozenset(t for lvl, t in index_of(list(pl.sea)) if lvl == level)
    return map_state.taken_tiles(level) | sea


def _sealed(zone: VegetatedZone, mine: frozenset[Tile]) -> VegetatedZone:
    return VegetatedZone(zone.open_set - mine, zone.passable - mine)


class VegetationStep(PipelineStep):
    """Corpus-fitted Gibbs marked-point-process vegetation, per zone.

    Config:
        seed     RNG seed.
        players  Number of player zones whose town spot stays clear of trees.

    inject(ctx): ``TerrainGrids`` (the tunnel cells) and ``Segmentation`` (TerrainStep's
    zones). The step builds the ``ZonePlan`` with ``zone_plan.plan_zones`` and
    ``zone_plan.plan_player_zones`` before any tree grows. Each ``PlanZone`` supplies the web,
    the rim, the entrance bands and the town room kept clear of trees.

    Produces: extends ``map_state.objs`` with this step's own new vegetation objects
    (``self.objs`` keeps just the new ones, for callers that want that distinction). Into ctx:
    the ``ZonePlan`` and ``VegetationResult``, which holds each zone's open and passable tiles.
    """

    def __init__(self, seed: int = 3, players: int = 0) -> None:
        self.seed: int = seed
        self.players: int = players
        self.objs: list[PlacedObject] = []
        self.log: list[str] = []
        self._ctx: ProviderRegistry = ProviderRegistry()
        self._terrain: TerrainGrids = TerrainGrids()
        self._segmentation: Segmentation = Segmentation({}, {})
        self._tunnel_protect: frozenset[Tile] = frozenset()

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx
        self._terrain = ctx.require(TerrainGrids)
        self._segmentation = ctx.require(Segmentation)
        self._tunnel_protect = self._terrain.tunnel_protect

    @override
    def run(self, catalog: Catalog, map_state: MapState) -> None:
        plan = self._zone_plan(catalog, map_state)
        models = vegetation_models(catalog, plan)
        pre_taken = {lvl: _taken(map_state, lvl, pl) for lvl, pl in plan.levels.items()}
        grown = {
            level: grow_level(models, self._grow_level(level, pl, pre_taken[level]), self.seed)
            for level, pl in plan.levels.items()
        }
        new_objs = [o for g in grown.values() for o in g.objs]
        self.objs = new_objs
        map_state.add_objs(new_objs, TerrainGate(catalog))
        veg: dict[int, dict[int, VegetatedZone]] = {}
        for level, pl in plan.levels.items():
            sealed = self._seal_level(catalog, map_state, level, pl, pre_taken[level])
            veg[level] = {
                zid: _sealed(v, sealed & pl.zones[zid].ts) for zid, v in grown[level].zones.items()
            }
            _check_islands(map_state, level, pl)
        self._ctx.provide(plan)
        self._ctx.provide(VegetationResult(log=tuple(self.log), zones=veg))

    def _zone_plan(self, catalog: Catalog, map_state: MapState) -> ZPL.ZonePlan:
        terrain = ZPL.PlanTerrain(
            self._segmentation, map_state.terrain, self._terrain.tunnel_protect
        )
        return ZPL.plan_player_zones(
            catalog,
            ZPL.plan_zones(catalog, terrain, self.seed),
            self._segmentation.zones,
            self._terrain.tunnel_protect,
            self.players,
        )

    def _grow_level(self, level: int, pl: ZPL.PlanLevel, taken: frozenset[Tile]) -> GrowLevel:
        zones = self._segmentation.zones[level]
        centroids = {zid: z.centroid for zid, z in zones.items()}
        return GrowLevel(level, pl, centroids, self._segmentation.zone_label[level], taken)

    def _seal_level(
        self,
        catalog: Catalog,
        map_state: MapState,
        level: int,
        pl: ZPL.PlanLevel,
        taken: frozenset[Tile],
    ) -> frozenset[Tile]:
        land: set[Tile] = set()
        bands: set[Tile] = set()
        avoid: set[Tile] = set(pl.landings.blk | pl.landings.appr)
        web: set[Tile] = set()
        avoid |= taken
        if level == 1:
            avoid |= self._tunnel_protect
        for zone in pl.zones.values():
            land |= zone.ts
            bands |= zone.ent_bands
            web |= zone.prot
            avoid |= zone.town.clear
        level_objs = [o for o in [*pl.sea, *map_state.objs] if o.level == level]
        sealers, sealed = seal_borders(
            catalog,
            BorderPlan(land, self._segmentation.zones[level], bands, avoid, web),
            level_objs,
            self.seed,
            level,
        )
        if not sealers:
            return NO_TILES
        self.objs.extend(sealers)
        map_state.add_objs(sealers, TerrainGate(catalog))
        self.log.append(f"L{level} border plan: {len(sealed)} cells closed")
        return frozenset(sealed)

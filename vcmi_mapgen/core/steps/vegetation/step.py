"""VegetationStep — place terrain-matched decorative vegetation per zone."""

from __future__ import annotations

from collections.abc import Mapping
from typing import override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.components import open_islands
from vcmi_mapgen.core.model import MapState, PlacedObject, Tile, Zone
from vcmi_mapgen.core.model.map_state import index_of
from vcmi_mapgen.core.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.planning import zone_plan as ZPL
from vcmi_mapgen.core.planning.content import ContentPlan, ContentPlanner, HopContent
from vcmi_mapgen.core.planning.loot_zones import choose_loot_zones
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.steps.terrain_gen.result import PlaceMap, Segmentation, TerrainGrids
from vcmi_mapgen.core.steps.vegetation.border_plan import BorderPlan, seal_borders
from vcmi_mapgen.core.steps.vegetation.grow import (
    GrowLevel,
    ground_patches,
    grow_level,
    vegetation_models,
)
from vcmi_mapgen.core.steps.vegetation.result import LootZones, VegetatedZone, VegetationResult
from vcmi_mapgen.core.steps.vegetation.sampler import Sampler

NO_TILES: frozenset[Tile] = frozenset()


def _land(zones: Mapping[int, Zone]) -> set[Tile]:
    return {t for z in zones.values() if not z.terrain_type.is_barrier for t in z.tiles_set}


def _check_islands(map_state: MapState, level: int, pl: ZPL.PlanLevel, land: set[Tile]) -> None:
    anchors: set[Tile] = set(pl.landings.blk | pl.landings.appr)
    for zone in pl.zones.values():
        anchors |= zone.prot
    blocking = {
        (cx, cy)
        for o in map_state.objs
        if o.level == level
        for cx, cy, blk in FP.anchored_cells(o.footprint, o.x, o.y)
        if blk
    }
    unreached = {t for island in open_islands(land, set(), anchors) for t in island}
    islands = open_islands(land - unreached, blocking, anchors)
    if islands:
        first = min(min(c) for c in islands)
        raise ValueError(
            f"VegetationStep: L{level} has {len(islands)} walled-off pocket(s) at {first}"
        )


def _taken(
    map_state: MapState, level: int, pl: ZPL.PlanLevel, doors: frozenset[Tile]
) -> frozenset[Tile]:
    sea = frozenset(t for lvl, t in index_of(list(pl.sea)) if lvl == level)
    return map_state.taken_tiles(level) | sea | doors


def _doors(places: PlaceMap, level: int) -> frozenset[Tile]:
    lp = places.levels.get(level)
    return frozenset(t for d in lp.territories.doors for t in d.tiles) if lp else NO_TILES


def _sealed(zone: VegetatedZone, mine: frozenset[Tile]) -> VegetatedZone:
    return VegetatedZone(zone.open_set - mine, zone.passable - mine)


def _loot_zones(map_state: MapState, plan: ZPL.ZonePlan) -> LootZones:
    homes = {lvl: {zid for lv, zid in plan.player_zids if lv == lvl} for lvl in plan.levels}
    return LootZones(
        {
            lvl: choose_loot_zones(
                {zid: z.ts for zid, z in pl.zones.items()},
                FP.blocking_cells([o for o in [*pl.sea, *map_state.objs] if o.level == lvl]),
                map_state.terrain.get(lvl, ()),
                homes[lvl],
            )
            for lvl, pl in plan.levels.items()
        }
    )


def _patches(
    catalog: Catalog, map_state: MapState, plan: ZPL.ZonePlan
) -> dict[int, dict[int, dict[str, frozenset[Tile]]]]:
    return {
        level: ground_patches(catalog, pl, map_state.terrain.get(level, ()))
        for level, pl in plan.levels.items()
    }


class VegetationStep(PipelineStep):
    """Corpus-fitted vegetation, per zone, grown by the configured sampler.

    Config:
        priors   The corpus priors; the step reads the vegetation and gameplay statistics.
        sampler  The algorithm that grows each zone's vegetation.
        seed     RNG seed.
        players  Number of player zones whose town spot stays clear of trees.
        content  The planner that reads each place's content intent off the place map.

    inject(ctx): ``TerrainGrids`` (the tunnel cells), ``Segmentation`` (TerrainStep's
    zones) and ``PlaceMap`` when present. The step asks ``content`` for the ``ContentPlan``,
    then builds the ``ZonePlan`` with ``zone_plan.plan_zones`` and
    ``zone_plan.plan_player_zones``, the plan's homes first, before any tree grows. Each
    ``PlanZone`` supplies the web, the rim, the entrance bands and the town room kept clear
    of trees.

    Produces: extends ``map_state.objs`` with this step's own new vegetation objects
    (``self.objs`` keeps just the new ones, for callers that want that distinction). Into ctx:
    the ``ContentPlan``, the ``ZonePlan``, ``VegetationResult``, which holds each zone's
    open and passable tiles, and ``LootZones``, the zones ``choose_loot_zones`` picks to be
    sealed once the trees stand.
    """

    def __init__(
        self,
        priors: Priors,
        sampler: Sampler,
        seed: int = 3,
        players: int = 0,
        content: ContentPlanner | None = None,
    ) -> None:
        self.priors: Priors = priors
        self.sampler: Sampler = sampler
        self.seed: int = seed
        self.players: int = players
        self.content: ContentPlanner = HopContent() if content is None else content
        self.objs: list[PlacedObject] = []
        self.log: list[str] = []
        self._ctx: ProviderRegistry = ProviderRegistry()
        self._terrain: TerrainGrids = TerrainGrids()
        self._segmentation: Segmentation = Segmentation({}, {})
        self._tunnel_protect: frozenset[Tile] = frozenset()
        self._places: PlaceMap = PlaceMap({})

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx
        self._terrain = ctx.require(TerrainGrids)
        self._segmentation = ctx.require(Segmentation)
        self._tunnel_protect = self._terrain.tunnel_protect
        self._places = ctx.get(PlaceMap, PlaceMap({}))

    @override
    def run(self, catalog: Catalog, map_state: MapState) -> None:
        content = self.content.plan(self.priors.places, self._places.levels)
        plan = self._zone_plan(catalog, map_state, content)
        patches = _patches(catalog, map_state, plan)
        terrains = sorted({name for lp in patches.values() for zp in lp.values() for name in zp})
        models = vegetation_models(catalog, self.priors.vegetation, plan, terrains)
        pre_taken = {
            lvl: _taken(map_state, lvl, pl, _doors(self._places, lvl))
            for lvl, pl in plan.levels.items()
        }
        grown = {
            level: grow_level(
                models,
                self._grow_level(map_state, level, pl, pre_taken[level], patches[level]),
                self.seed,
                self.sampler,
            )
            for level, pl in plan.levels.items()
        }
        new_objs = [o for g in grown.values() for o in g.objs]
        self.objs = new_objs
        map_state.add_objs(new_objs)
        veg: dict[int, dict[int, VegetatedZone]] = {}
        for level, pl in plan.levels.items():
            sealed = self._seal_level(catalog, map_state, level, pl, pre_taken[level])
            veg[level] = {
                zid: _sealed(v, sealed & pl.zones[zid].ts) for zid, v in grown[level].zones.items()
            }
            _check_islands(map_state, level, pl, _land(self._segmentation.zones[level]))
        self._ctx.provide(content)
        self._ctx.provide(plan)
        self._ctx.provide(VegetationResult(log=tuple(self.log), zones=veg))
        self._ctx.provide(_loot_zones(map_state, plan))

    def _zone_plan(
        self, catalog: Catalog, map_state: MapState, content: ContentPlan
    ) -> ZPL.ZonePlan:
        seg = self._segmentation
        terrain = ZPL.PlanTerrain(
            seg.zones,
            seg.zone_label,
            map_state.terrain,
            {level: lp.passages for level, lp in self._places.levels.items()},
        )
        return ZPL.plan_player_zones(
            catalog,
            ZPL.plan_zones(catalog, terrain, self.priors.gameplay, self.seed),
            self._segmentation.zones,
            self._terrain.tunnel_protect,
            ZPL.HomeRequest(self.players, content.homes, map_state.size),
        )

    def _grow_level(
        self,
        map_state: MapState,
        level: int,
        pl: ZPL.PlanLevel,
        taken: frozenset[Tile],
        patches: Mapping[int, Mapping[str, frozenset[Tile]]],
    ) -> GrowLevel:
        zones = self._segmentation.zones[level]
        centroids = {zid: z.centroid for zid, z in zones.items()}
        label = self._segmentation.zone_label[level]
        ground = map_state.terrain.get(level, ())
        return GrowLevel(level, pl, centroids, label, taken, ground, patches)

    def _seal_level(
        self,
        catalog: Catalog,
        map_state: MapState,
        level: int,
        pl: ZPL.PlanLevel,
        taken: frozenset[Tile],
    ) -> frozenset[Tile]:
        land = _land(self._segmentation.zones[level])
        bands: set[Tile] = set()
        avoid: set[Tile] = set(pl.landings.blk | pl.landings.appr)
        web: set[Tile] = set(pl.landings.blk | pl.landings.appr) | _doors(self._places, level)
        avoid |= taken
        if level == 1:
            avoid |= self._tunnel_protect
        ends: set[tuple[Tile, int]] = set()
        for zone in pl.zones.values():
            bands |= zone.ent_bands
            ends |= {(t, e.other) for e in zone.entrances for t in e.band}
            web |= zone.prot
            avoid |= zone.town.clear
        level_objs = [o for o in [*pl.sea, *map_state.objs] if o.level == level]
        sealers, sealed = seal_borders(
            catalog,
            BorderPlan(
                land,
                self._segmentation.zones[level],
                bands,
                avoid,
                web,
                map_state.terrain.get(level, ()),
                pl.open_pairs,
                ends,
            ),
            level_objs,
            self.seed,
            level,
        )
        if not sealers:
            return NO_TILES
        self.objs.extend(sealers)
        map_state.add_objs(sealers)
        self.log.append(f"L{level} border plan: {len(sealed)} cells closed")
        return frozenset(sealed)

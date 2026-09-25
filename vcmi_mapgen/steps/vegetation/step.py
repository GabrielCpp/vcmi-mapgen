"""VegetationStep — place terrain-matched decorative vegetation per zone."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import override

from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.models import MapState, PlacedObject, Tile
from vcmi_mapgen.ontology import Ontology
from vcmi_mapgen.pipeline import LevelWorkspace, PipelineStep, PlacementWorkspace, ProviderRegistry
from vcmi_mapgen.steps.terrain_gen.step import TerrainGrids
from vcmi_mapgen.steps.vegetation import sample as PP
from vcmi_mapgen.steps.vegetation.border_plan import seal_borders
from vcmi_mapgen.steps.vegetation.islands import open_islands
from vcmi_mapgen.validate import TerrainGate


@dataclass
class VegetationResult:
    """Diagnostic log lines for the CLI to print."""

    log: list[str] = field(default_factory=list)


class VegetationStep(PipelineStep):
    """Corpus-fitted Gibbs marked-point-process vegetation, per zone.

    Config:
        seed  RNG seed.

    Reads ``map_state.zones`` (SegmentStep's output) directly in run(). inject(ctx):
    the folded-in ``workspace`` (a ``PlacementWorkspace``, written by GameplayStep);
    each zone's ``ZoneWorkspace`` supplies ``prot``/``occupied``/``gblocked``/
    ``approaches``/``gobjs``/``rim8``/``ent_bands``, and this step writes
    ``blocked``/``open_set``/``passable`` back into the same object for
    PickupStep.

    Produces: extends ``map_state.objs`` with this step's own new vegetation objects
    (``self.objs`` keeps just the new ones, for callers that want that distinction).
    """

    def __init__(self, seed: int = 3) -> None:
        self.seed: int = seed
        self.objs: list[PlacedObject] = []
        self.log: list[str] = []
        self._ctx: ProviderRegistry = ProviderRegistry()
        self._workspace: PlacementWorkspace | None = None
        self._tunnel_protect: frozenset[Tile] = frozenset()

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx
        self._workspace = ctx.require(PlacementWorkspace)
        self._tunnel_protect = ctx.require(TerrainGrids).tunnel_protect

    @override
    def run(self, ontology: Ontology, map_state: MapState) -> None:
        if self._workspace is None:
            raise RuntimeError("VegetationStep.run() requires inject() to have been called")
        models: dict[str, PP.VegModel] = {}
        new_objs: list[PlacedObject] = []
        pre_taken = {lvl: map_state.taken_tiles(lvl) for lvl in self._workspace.levels}

        for level, lvl_ws in self._workspace.levels.items():
            for zid, zw in lvl_ws.zones.items():
                zones = map_state.zones[level]
                terrain = zw.terrain
                ts = zw.ts
                ts_full = zw.ts_full

                if terrain not in models:
                    models[terrain] = PP.build_model(terrain)
                model = models[terrain]
                if not model.cats:
                    continue

                # Seaport footprint in this zone must be excluded from vegetation
                zone_seaport_cells = (lvl_ws.seaport_blk | lvl_ws.seaport_appr) & ts_full
                forbid = map_state.taken_tiles(level) | zone_seaport_cells
                mine_cells = {
                    (mcx, mcy)
                    for o in zw.gobjs
                    if o.purpose == "MINE"
                    for mcx, mcy, mblk in OR.mask_cells(o.mask, o.x, o.y)
                    if mblk
                }
                # annulus 2..3: greenery frames the mine without sprite canopies overhanging
                # its visual
                attract = (
                    frozenset(
                        t
                        for t in ts
                        if t not in forbid
                        and 2
                        <= min(max(abs(t[0] - mx), abs(t[1] - my)) for mx, my in mine_cells)
                        <= 3
                    )
                    if mine_cells
                    else frozenset[Tile]()
                )
                # zone-isolation border belt: the whole 8-connected rim minus the planned
                # entrance bands (those sit in `prot` as hard zeros) gets the +BORDER_W
                # vegetation bias — both zones densify their own side, so the border reads
                # as a ~2-thick ridge.
                border = frozenset(zw.rim8 - zw.ent_bands - forbid)
                zobjs, blocked, _ = PP.sample_zone(
                    ts,
                    zones,
                    zid,
                    model,
                    seed=self.seed,
                    prot=zw.prot,
                    forbid=forbid,
                    attract=attract,
                    border=border,
                    impassable=zw.gblocked,
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
        map_state.set_objs(map_state.objs + new_objs, TerrainGate(ontology))
        for level, lvl_ws in self._workspace.levels.items():
            self._seal_level(ontology, map_state, level, lvl_ws, pre_taken[level])
        for level, lvl_ws in self._workspace.levels.items():
            land: set[Tile] = set()
            anchors: set[Tile] = set(lvl_ws.seaport_blk | lvl_ws.seaport_appr)
            for zw in lvl_ws.zones.values():
                land |= zw.ts_full
                anchors |= zw.prot | set(zw.approaches)
            blocking = {
                (cx, cy)
                for o in map_state.objs
                if o.level == level
                for cx, cy, blk in OR.mask_cells(o.mask, o.x, o.y)
                if blk
            }
            islands = open_islands(land, blocking, anchors)
            if islands:
                first = min(min(c) for c in islands)
                raise ValueError(
                    f"VegetationStep: L{level} has {len(islands)} walled-off pocket(s) at {first}"
                )
        self._ctx.provide(VegetationResult(log=self.log))

    def _seal_level(
        self,
        ontology: Ontology,
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
            avoid |= set(zw.approaches)
        level_objs = [o for o in map_state.objs if o.level == level]
        sealers, sealed = seal_borders(
            land, map_state.zones[level], level_objs, bands, avoid, web, self.seed, level
        )
        if not sealers:
            return
        if level == 1:
            for o in sealers:
                o.level = 1
        self.objs.extend(sealers)
        map_state.set_objs(map_state.objs + sealers, TerrainGate(ontology))
        for zw in lvl_ws.zones.values():
            mine = sealed & zw.ts_full
            zw.blocked |= mine
            zw.open_set -= mine
            zw.passable -= mine
        self.log.append(f"L{level} border plan: {len(sealed)} cells closed")

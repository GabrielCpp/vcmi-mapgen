"""GameplayStep: dwellings, banks and visitables placed against the vegetated field."""

from __future__ import annotations

from typing import final, override

from vcmi_mapgen.models import CoverIndex, MapState, PlacedObject, Tile
from vcmi_mapgen.ontology import Ontology
from vcmi_mapgen.pipeline import LevelWorkspace, PipelineStep, PlacementWorkspace, ProviderRegistry
from vcmi_mapgen.steps.gameplay.attractions import LevelField, place_attractions
from vcmi_mapgen.steps.terrain_gen.step import TerrainGrids
from vcmi_mapgen.validate import TerrainGate

NO_TILES: frozenset[Tile] = frozenset()


@final
class GameplayStep(PipelineStep):
    """Emit the attractions TownsStep planned for each zone once vegetation has grown around them.

    Config:
        seed        RNG seed.

    inject(ctx): ``PlacementWorkspace`` (each zone's ``planned`` objects and post-vegetation
    field), ``TerrainGrids`` (the underground tunnel cells no footprint may take).

    Produces: appends the attractions to ``map_state.objs`` and folds them into each
    ``ZoneWorkspace`` (``gobjs``, ``occupied``, ``gblocked``, ``approaches``, ``open_set``,
    ``passable``, ``prot``) so every later step respects them.
    """

    def __init__(self, seed: int = 3) -> None:
        self.seed = seed
        self.objs: list[PlacedObject] = []
        self._workspace = PlacementWorkspace()
        self._tunnel_protect: frozenset[Tile] = NO_TILES

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._workspace = ctx.get_or_create(PlacementWorkspace, PlacementWorkspace)
        self._tunnel_protect = ctx.require(TerrainGrids).tunnel_protect

    @override
    def run(self, ontology: Ontology, map_state: MapState) -> None:
        gate = TerrainGate(ontology)
        for level, lw in sorted(self._workspace.levels.items()):
            field = LevelField(
                level=level,
                seed=self.seed,
                taken=map_state.taken_tiles(level),
                reserved=lw.seaport_appr,
                avoid=self._tunnel_protect if level == 1 else NO_TILES,
                covers=CoverIndex(o for o in map_state.objs if o.level == level),
                legal=lambda o: not gate.check(o, map_state.cells),
            )
            self.objs.extend(self._place_level(lw, field))
        map_state.add_objs(self.objs, gate)

    @staticmethod
    def _place_level(lw: LevelWorkspace, field: LevelField) -> list[PlacedObject]:
        out: list[PlacedObject] = []
        for zid, zw in sorted(lw.zones.items()):
            out.extend(place_attractions(zid, zw, field))
        return out

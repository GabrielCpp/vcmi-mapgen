"""BorderStep: closes every zone border outside the planned entrances."""

from __future__ import annotations

from typing import final, override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState, PlacedObject, Tile
from vcmi_mapgen.core.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.core.planning.zone_index import ZoneIndex
from vcmi_mapgen.core.planning.zone_plan import ZonePlan
from vcmi_mapgen.core.steps.border import crossings as BS
from vcmi_mapgen.core.steps.border.guard import BorderLevel, guard_level
from vcmi_mapgen.core.steps.border.result import BorderResult
from vcmi_mapgen.core.steps.gameplay.result import TownsIndex
from vcmi_mapgen.core.steps.terrain_gen.result import Segmentation


@final
class BorderStep(PipelineStep):
    """Entrance guards on most planned zone entrances, then a guard on every other
    cross-zone crossing left open.

    Config:
        seed        RNG seed.
        size        Map side length in tiles (square).

    inject(ctx): ``ZoneIndex`` (zone records and ``hard_avoid``), ``ZonePlan`` (the entrance
    plan), ``Segmentation``, ``TownsIndex`` (player zones).

    Produces: appends the guards and seals to ``map_state.objs`` and provides ``BorderResult``
    with each level's guard tiles.
    """

    def __init__(self, seed: int = 3, size: int = 72) -> None:
        self.seed = seed
        self.size = size
        self.objs: list[PlacedObject] = []
        self.log: list[str] = []
        self._ctx = ProviderRegistry()
        self._zones = ZoneIndex()
        self._plan = ZonePlan({}, ())
        self._segmentation = Segmentation({}, {})
        self._player_zids: list[tuple[int, int]] = []

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx
        self._zones = ctx.require(ZoneIndex)
        self._plan = ctx.require(ZonePlan)
        self._segmentation = ctx.require(Segmentation)
        self._player_zids = ctx.require(TownsIndex).player_zids

    @override
    def run(self, catalog: Catalog, map_state: MapState) -> None:
        grids = map_state.terrain
        by_level = map_state.objs_by_level(grids)
        guards: dict[int, frozenset[Tile]] = {}
        for level in sorted(grids):
            lv = BorderLevel(
                BS.LevelGrid(
                    self.size, self.size, grids[level], self._segmentation.zones[level], level
                ),
                self._plan.levels[level].entrance_plan,
                self._zones.zone_records[level],
                frozenset(zid for lvl, zid in self._player_zids if lvl == level),
                self._zones.hard_avoid[level],
            )
            guarded = guard_level(catalog, lv, by_level[level], self.seed)
            self.objs.extend(guarded.objs)
            if guarded.guard_tiles or guarded.n_open:
                self.log.append(
                    f"L{level} border guards: {len(guarded.guard_tiles)}"
                    + (
                        f", {guarded.n_open} crossings left free (unguardable)"
                        if guarded.n_open
                        else ""
                    )
                )
            guards[level] = guarded.guard_tiles

        map_state.add_objs(self.objs)
        self._ctx.provide(BorderResult(log=self.log, guard_tiles=guards))

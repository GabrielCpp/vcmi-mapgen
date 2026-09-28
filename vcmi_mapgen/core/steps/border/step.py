"""BorderStep: closes every zone border outside the planned entrances."""

from __future__ import annotations

from typing import final, override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState, PlacedObject, Tile
from vcmi_mapgen.core.pipeline import (
    LevelWorkspace,
    PipelineStep,
    PlacementWorkspace,
    ProviderRegistry,
)
from vcmi_mapgen.core.placement.rules import TerrainGate
from vcmi_mapgen.core.planning.zone_index import ZoneIndex, ZoneRecord
from vcmi_mapgen.core.steps.border import crossings as BS
from vcmi_mapgen.core.steps.border.entrances import EntranceField, guard_entrances
from vcmi_mapgen.core.steps.border.result import BorderResult
from vcmi_mapgen.core.steps.gameplay.result import TownsIndex
from vcmi_mapgen.core.steps.terrain_gen.result import Segmentation


def _loot_tiles(zone_records: list[ZoneRecord]) -> set[Tile]:
    loot_ts: set[Tile] = set()
    for zr in zone_records:
        if zr.loot_zone:
            loot_ts |= zr.ts
    return loot_ts


def _entrance_bands(lvl_ws: LevelWorkspace) -> set[Tile]:
    bands: set[Tile] = set()
    for ents in lvl_ws.entrance_plan.values():
        for _r, b, _o in ents:
            bands |= b
    return bands


def _entrance_field(
    lvl_ws: LevelWorkspace, zone_records: list[ZoneRecord], home_zids: set[int]
) -> EntranceField:
    return EntranceField(
        plan=lvl_ws.entrance_plan,
        zone_tiles={zr.zid: zr.ts for zr in zone_records},
        home_zids=home_zids,
        skip_zids={zr.zid for zr in zone_records if zr.loot_zone},
        avoid=lvl_ws.hard_avoid,
    )


@final
class BorderStep(PipelineStep):
    """Entrance guards on most planned zone entrances, then a guard on every other
    cross-zone crossing left open.

    Config:
        seed        RNG seed.
        size        Map side length in tiles (square).

    inject(ctx): ``ZoneIndex`` (zone records), ``Segmentation``, ``TownsIndex``
    (player zones), the shared
    ``PlacementWorkspace`` (``entrance_plan``/``seal_avoid``/``hard_avoid``; writes
    ``guard_tiles`` back per level).

    Produces: appends the guards and seals to ``map_state.objs`` and provides ``BorderResult``.
    """

    def __init__(self, seed: int = 3, size: int = 72) -> None:
        self.seed = seed
        self.size = size
        self.objs: list[PlacedObject] = []
        self.log: list[str] = []
        self._ctx = ProviderRegistry()
        self._zone_records: dict[int, list[ZoneRecord]] = {}
        self._segmentation = Segmentation({}, {})
        self._workspace = PlacementWorkspace()
        self._player_zids: list[tuple[int, int]] = []

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx
        self._zone_records = ctx.require(ZoneIndex).zone_records
        self._segmentation = ctx.require(Segmentation)
        self._workspace = ctx.require(PlacementWorkspace)
        self._player_zids = ctx.require(TownsIndex).player_zids

    @override
    def run(self, catalog: Catalog, map_state: MapState) -> None:
        W = H = self.size
        grids = map_state.terrain
        objs_by_level: dict[int, list[PlacedObject]] = {lvl: [] for lvl in grids}
        for o in map_state.objs:
            if o.level in objs_by_level:
                objs_by_level[o.level].append(o)

        for level in sorted(grids):
            lvl_ws = self._workspace.levels[level]
            zone_records = self._zone_records[level]
            loot_ts = _loot_tiles(zone_records)
            bands = _entrance_bands(lvl_ws)
            home_zids = {zid for lvl, zid in self._player_zids if lvl == level}
            ent_objs = guard_entrances(
                catalog,
                _entrance_field(lvl_ws, zone_records, home_zids),
                objs_by_level[level],
                self.seed,
                level,
            )
            objs_by_level[level].extend(ent_objs)
            self.objs.extend(ent_objs)
            new_objs, guard_tiles, n_open = BS.guard_crossings(
                catalog,
                BS.LevelGrid(W, H, grids[level], self._segmentation.zones[level], level),
                BS.CrossingRules(bands, lvl_ws.hard_avoid, skip_tiles=loot_ts),
                objs_by_level[level],
                self.seed,
            )
            objs_by_level[level].extend(new_objs)
            self.objs.extend(new_objs)
            guard_tiles |= {(o.x, o.y) for o in ent_objs}
            if guard_tiles or n_open:
                self.log.append(
                    f"L{level} border guards: {len(guard_tiles)}"
                    + (f", {n_open} crossings left free (unguardable)" if n_open else "")
                )
            for zr in zone_records:
                zr.open_set -= guard_tiles
            lvl_ws.guard_tiles = frozenset(guard_tiles)

        map_state.add_objs(self.objs, TerrainGate(catalog))
        self._ctx.provide(BorderResult(log=self.log))

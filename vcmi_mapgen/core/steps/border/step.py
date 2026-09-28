"""BorderStep: closes every zone border outside the planned entrances."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import final, override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Entrance, MapState, PlacedObject, Tile
from vcmi_mapgen.core.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.core.placement.rules import TerrainGate
from vcmi_mapgen.core.planning.zone_index import ZoneIndex, ZoneRecord
from vcmi_mapgen.core.planning.zone_plan import ZonePlan
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


def _entrance_bands(entrance_plan: Mapping[int, Sequence[Entrance]]) -> set[Tile]:
    bands: set[Tile] = set()
    for ents in entrance_plan.values():
        for _r, b, _o in ents:
            bands |= b
    return bands


def _entrance_field(
    entrance_plan: Mapping[int, list[Entrance]],
    zone_records: list[ZoneRecord],
    home_zids: set[int],
    avoid: frozenset[Tile],
) -> EntranceField:
    return EntranceField(
        plan=entrance_plan,
        zone_tiles={zr.zid: zr.ts for zr in zone_records},
        home_zids=home_zids,
        skip_zids={zr.zid for zr in zone_records if zr.loot_zone},
        avoid=avoid,
    )


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
        W = H = self.size
        grids = map_state.terrain
        objs_by_level: dict[int, list[PlacedObject]] = {lvl: [] for lvl in grids}
        for o in map_state.objs:
            if o.level in objs_by_level:
                objs_by_level[o.level].append(o)

        guards: dict[int, frozenset[Tile]] = {}
        for level in sorted(grids):
            entrance_plan = self._plan.levels[level].entrance_plan
            hard_avoid = self._zones.hard_avoid[level]
            zone_records = self._zones.zone_records[level]
            loot_ts = _loot_tiles(zone_records)
            bands = _entrance_bands(entrance_plan)
            home_zids = {zid for lvl, zid in self._player_zids if lvl == level}
            ent_objs = guard_entrances(
                catalog,
                _entrance_field(entrance_plan, zone_records, home_zids, hard_avoid),
                objs_by_level[level],
                self.seed,
                level,
            )
            objs_by_level[level].extend(ent_objs)
            self.objs.extend(ent_objs)
            new_objs, guard_tiles, n_open = BS.guard_crossings(
                catalog,
                BS.LevelGrid(W, H, grids[level], self._segmentation.zones[level], level),
                BS.CrossingRules(bands, hard_avoid, skip_tiles=loot_ts),
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
            guards[level] = frozenset(guard_tiles)

        map_state.add_objs(self.objs, TerrainGate(catalog))
        self._ctx.provide(BorderResult(log=self.log, guard_tiles=guards))

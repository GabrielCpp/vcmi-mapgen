"""GatedStep: seals small one-passage zones behind a Border Gate or a monolith pair."""

from __future__ import annotations

from dataclasses import replace
from typing import final, override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState, PlacedObject, Tile
from vcmi_mapgen.core.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.core.placement.rules import TerrainGate
from vcmi_mapgen.core.planning.zone_index import build_zone_index
from vcmi_mapgen.core.planning.zone_plan import ZonePlan
from vcmi_mapgen.core.steps.gameplay.result import GameplayResult
from vcmi_mapgen.core.steps.gated.placer import place_gated_zones
from vcmi_mapgen.core.steps.gated.result import GatedResult


def _report_loot(level: int, n_loot: int, loot_zids: set[int]) -> None:
    if n_loot:
        zid_str = ", ".join(str(z) for z in sorted(loot_zids))
        print(
            f"  L{level} loot zones: {n_loot} access pair(s) placed "
            + f"(1 gate+key, {n_loot - 1} sealed+monolith) zones=[{zid_str}]"
            if n_loot > 1
            else f"  L{level} loot zones: 1 gate+key pair placed zones=[{zid_str}]"
        )


@final
class GatedStep(PipelineStep):
    """Loot-zone access: each small zone with a single passage is sealed with blocking
    decoration, and its only way in becomes a Border Gate with a guarded Keymaster outside,
    or a monolith pair with a guarded partner outside.

    Config:
        seed        RNG seed.
        size        Map side length in tiles (square).

    inject(ctx): ``ZonePlan`` (each zone's plan) and ``GameplayResult`` (each zone after
    placement and the recomputed seaport landings).

    Produces: appends the gates, monoliths, partners, guards and seals to ``map_state.objs``,
    and provides ``ZoneIndex`` and ``GatedResult``.
    """

    def __init__(self, seed: int = 3, size: int = 72) -> None:
        self.seed = seed
        self.size = size
        self.objs: list[PlacedObject] = []
        self._ctx = ProviderRegistry()
        self._plan = ZonePlan({}, ())
        self._gameplay = GameplayResult({}, {}, {})

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx
        self._plan = ctx.require(ZonePlan)
        self._gameplay = ctx.require(GameplayResult)

    @override
    def run(self, catalog: Catalog, map_state: MapState) -> None:
        index = build_zone_index(self._plan, self._gameplay.zones, self._gameplay.landings)
        by_level: dict[int, list[PlacedObject]] = {lvl: [] for lvl in index.zone_records}
        for o in map_state.objs:
            if o.level in by_level:
                by_level[o.level].append(o)
        result = GatedResult()
        for level, zone_records in index.zone_records.items():
            new, n, access, claims = place_gated_zones(
                catalog,
                zone_records,
                by_level[level],
                seed=self.seed,
                bounds=(self.size, self.size),
            )
            for o in new:
                o.level = level
            interior: set[Tile] = set()
            for zr in zone_records:
                if zr.zid in access:
                    interior |= zr.ts
            index.zone_records[level] = [
                replace(zr, loot_zone=True) if zr.zid in access else zr for zr in zone_records
            ]
            targets = index.targets[level]
            targets.extend((o.x, o.y) for o in new if o.purpose)
            targets[:] = [t for t in targets if t not in interior]
            result.access[level] = access
            index.claims[level] = claims
            self.objs.extend(new)
            _report_loot(level, n, set(access))
        map_state.add_objs(self.objs, TerrainGate(catalog))
        self._ctx.provide(index)
        self._ctx.provide(result)

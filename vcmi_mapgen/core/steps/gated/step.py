"""GatedStep: seals small one-passage zones behind a Border Gate or a monolith pair."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import final, override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState, PlacedObject, Tile
from vcmi_mapgen.core.pipeline import PipelineStep, PlacementWorkspace, ProviderRegistry
from vcmi_mapgen.core.placement.rules import TerrainGate
from vcmi_mapgen.core.planning.zone_index import build_zone_index
from vcmi_mapgen.core.steps.gated.placer import LootAccess, place_gated_zones


@dataclass
class GatedResult:
    """The access of every loot zone, per level and zone id."""

    access: dict[int, dict[int, LootAccess]] = field(default_factory=dict)


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

    inject(ctx): the shared ``PlacementWorkspace``.

    Produces: appends the gates, monoliths, partners, guards and seals to ``map_state.objs``,
    and provides ``ZoneIndex`` and ``GatedResult``.
    """

    def __init__(self, seed: int = 3, size: int = 72) -> None:
        self.seed = seed
        self.size = size
        self.objs: list[PlacedObject] = []
        self._ctx = ProviderRegistry()
        self._workspace = PlacementWorkspace()

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx
        self._workspace = ctx.require(PlacementWorkspace)

    @override
    def run(self, catalog: Catalog, map_state: MapState) -> None:
        index = build_zone_index(self._workspace)
        by_level: dict[int, list[PlacedObject]] = {lvl: [] for lvl in index.zone_records}
        for o in map_state.objs:
            if o.level in by_level:
                by_level[o.level].append(o)
        result = GatedResult()
        for level, zone_records in index.zone_records.items():
            new, n, access = place_gated_zones(
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
                    zr.loot_zone = True
            targets = index.targets[level]
            targets.extend((o.x, o.y) for o in new if o.purpose)
            targets[:] = [t for t in targets if t not in interior]
            result.access[level] = access
            self.objs.extend(new)
            _report_loot(level, n, set(access))
        map_state.add_objs(self.objs, TerrainGate(catalog))
        self._ctx.provide(index)
        self._ctx.provide(result)

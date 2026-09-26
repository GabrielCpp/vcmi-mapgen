"""ScatterStep — free resource piles, the last thing placed on the map."""

from __future__ import annotations

import collections
from typing import override

from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.models import CoverIndex, MapState, PlacedObject, Tile
from vcmi_mapgen.ontology import Ontology
from vcmi_mapgen.pipeline import PipelineStep, PlacementWorkspace, ProviderRegistry
from vcmi_mapgen.steps.placement import guard_zoc
from vcmi_mapgen.steps.scatter import scatter as SC
from vcmi_mapgen.steps.zone_index import ZoneIndex
from vcmi_mapgen.validate import TerrainGate


class ScatterStep(PipelineStep):
    """Free resource piles over the open field, after every guard, portal rescue, cache and
    loot zone. A pile never sits inside a guard's zone of control, so a free resource beside
    a monster does not look guarded, and it never claims a tile an earlier step used.

    Config:
        seed       RNG seed.
        size       Map side length in tiles (square).

    inject(ctx): ``ZoneIndex`` (zone records), the shared ``PlacementWorkspace``.

    Produces: appends the piles to ``map_state.objs``.
    """

    def __init__(self, seed: int = 3, size: int = 72) -> None:
        self.seed: int = seed
        self.size: int = size
        self.objs: list[PlacedObject] = []
        self._zones: ZoneIndex = ZoneIndex()
        self._workspace: PlacementWorkspace = PlacementWorkspace()

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._zones = ctx.require(ZoneIndex)
        self._workspace = ctx.require(PlacementWorkspace)

    @override
    def run(self, ontology: Ontology, map_state: MapState) -> None:
        by_level: dict[int, list[PlacedObject]] = {lvl: [] for lvl in self._zones.zone_records}
        for o in map_state.objs:
            if o.level in by_level:
                by_level[o.level].append(o)

        for level, zone_records in self._zones.zone_records.items():
            level_objs = by_level[level]
            taken: set[Tile] = {
                (cx, cy) for o in level_objs for cx, cy, _b in OR.mask_cells(o.mask, o.x, o.y)
            }
            cover = CoverIndex(level_objs)
            zoc = guard_zoc(level_objs)
            lvl_ws = self._workspace.levels[level]
            for zr in zone_records:
                if zr.loot_zone:
                    continue
                zw = lvl_ws.zones[zr.zid]
                used = set(zr.used) | taken
                piles, _u, _r = SC.place_scatter(
                    SC.ScatterZone(
                        zw.ts,
                        map_state.zones[level],
                        zr.zid,
                        zw.terrain,
                        zw.open_set - (zw.rim8 - zw.ent_bands),
                        zw.prot,
                        entrances=zw.entrances,
                    ),
                    SC.ScatterConfig(
                        seed=self.seed,
                        bounds=(self.size, self.size),
                        cover=cover,
                        reach_in=set(zr.reach),
                        used_in=used,
                        avoid=zoc,
                    ),
                )
                for o in piles:
                    o.level = level
                taken |= used
                level_objs.extend(piles)
                self.objs.extend(piles)
                pk = collections.Counter(o.purpose for o in piles)
                print(
                    f"  L{level} zone {zr.zid:>3} {zw.terrain:<8} {len(zw.ts_full):>5} tiles: "
                    + f"scatter res={pk.get('RESOURCE_PILE', 0)}"
                )

        map_state.add_objs(self.objs, TerrainGate(ontology))

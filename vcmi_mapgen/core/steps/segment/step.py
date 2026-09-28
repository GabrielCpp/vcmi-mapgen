"""SegmentStep — flood-fill zone segmentation per level."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.segment import ZoneLabel, segment_level
from vcmi_mapgen.core.model import MapState, Tile, Zone
from vcmi_mapgen.core.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.core.steps.terrain_gen.step import TerrainGrids


@dataclass(frozen=True, slots=True)
class Segmentation:
    """Each level's zones and its zone label grid, read ``[y][x]``, -1 on a barrier tile."""

    zones: Mapping[int, Mapping[int, Zone]]
    zone_label: Mapping[int, ZoneLabel]


def _warn_sliver_zones(
    zones: Mapping[int, Zone], level: int, protect: frozenset[Tile] | None = None
) -> None:
    min_area = 25
    guard: frozenset[Tile] = frozenset() if protect is None else protect
    for zid, z in zones.items():
        if z.area < min_area and not (z.tiles_set & guard):
            print(
                f"  WARNING: level {level} zone {zid} is very small ({z.area} tiles, "
                + f"terrain {z.terrain_type})"
            )


class SegmentStep(PipelineStep):
    """Segment each active level's tile grid into same-terrain zones.

    Reads ``map_state.cells`` (TerrainStep's output) directly in run().
    inject(ctx): ``TerrainGrids`` (TerrainStep's output, for tunnel_protect).

    Produces: ``zones``, written directly onto MapState, and ``Segmentation``.
    """

    def __init__(self) -> None:
        self.zones: dict[int, dict[int, Zone]] = {}
        self._tunnel_protect: frozenset[Tile] = frozenset()
        self._ctx: ProviderRegistry = ProviderRegistry()

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx
        self._tunnel_protect = ctx.require(TerrainGrids).tunnel_protect

    @override
    def run(self, catalog: Catalog, map_state: MapState) -> None:
        protect = self._tunnel_protect
        labels: dict[int, ZoneLabel] = {}
        for level, cells in map_state.cells.items():
            zones, labels[level], _ = segment_level(cells)
            _warn_sliver_zones(zones, level, protect=protect if level == 1 else frozenset())
            self.zones[level] = zones
        map_state.zones = self.zones
        self._ctx.provide(Segmentation(self.zones, labels))

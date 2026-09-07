"""SegmentStep — flood-fill zone segmentation per level."""
from __future__ import annotations

from vcmi_mapgen.pipeline import PipelineStep
from vcmi_mapgen.kit.segmentation import _segment_level
from vcmi_mapgen.steps.terrain_gen.step import TerrainGrids


def _warn_sliver_zones(zones, level, protect=frozenset()):
    MIN_AREA = 25
    for zid, z in zones.items():
        if z["area"] < MIN_AREA and not (frozenset(z.get("tiles_set", [])) & protect):
            print(f"  WARNING: level {level} zone {zid} is very small "
                  f"({z['area']} tiles, terrain {z.get('terrain_type')})")


class SegmentStep(PipelineStep):
    """Segment each active level's tile grid into same-terrain zones.

    Reads ``map_state.cells`` (TerrainStep's output) directly in run().
    inject(ctx): ``TerrainGrids`` (TerrainStep's output, for tunnel_protect).

    Produces: ``zones``, written directly onto MapState.
    """

    def __init__(self) -> None:
        self.zones: dict = {}
        self._tunnel_protect: frozenset = frozenset()

    def inject(self, ctx) -> None:
        self._tunnel_protect = ctx.require(TerrainGrids).tunnel_protect

    def run(self, ontology, map_state) -> None:
        protect = self._tunnel_protect
        for level, cells in map_state.cells.items():
            zones, _zl, _ = _segment_level(cells)
            _warn_sliver_zones(zones, level,
                               protect=protect if level == 1 else frozenset())
            self.zones[level] = zones
        map_state.zones = self.zones

"""SegmentStep — flood-fill zone segmentation per level."""
from __future__ import annotations

from vcmi_mapgen.pipeline import PipelineStep
from vcmi_mapgen.kit.segmentation import _segment_level


def _warn_sliver_zones(zones, level, protect=frozenset()):
    MIN_AREA = 25
    for zid, z in zones.items():
        if z["area"] < MIN_AREA and not (frozenset(z.get("tiles_set", [])) & protect):
            print(f"  WARNING: level {level} zone {zid} is very small "
                  f"({z['area']} tiles, terrain {z.get('terrain_type')})")


class SegmentStep(PipelineStep):
    """Segment each active level's tile grid into same-terrain zones.

    inject(cells, tunnel_protect): ``cells`` (TileStep's output) and
    ``tunnel_protect`` (TerrainGenStep's output).

    Produces: ``zones``.
    """

    def __init__(self) -> None:
        self.zones: dict = {}
        self._cells: dict = {}
        self._tunnel_protect: frozenset = frozenset()

    def inject(self, *, cells: dict, tunnel_protect) -> None:
        self._cells = cells
        self._tunnel_protect = frozenset(tunnel_protect)

    def run(self) -> None:
        protect = self._tunnel_protect
        for level, cells in self._cells.items():
            zones, _zl, _ = _segment_level(cells)
            _warn_sliver_zones(zones, level,
                               protect=protect if level == 1 else frozenset())
            self.zones[level] = zones

"""TerrainStep's results."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from vcmi_mapgen.core.grid.segment import ZoneLabel
from vcmi_mapgen.core.model import Tile, Zone


@dataclass
class TerrainGrids:
    """The underground tunnel cells despeckle kept open. The terrain itself is
    ``MapState.terrain``."""

    tunnel_protect: frozenset[Tile] = frozenset()


@dataclass(frozen=True, slots=True)
class Segmentation:
    """Each level's zones and its zone label grid, read ``[y][x]``, -1 on a barrier tile."""

    zones: Mapping[int, Mapping[int, Zone]]
    zone_label: Mapping[int, ZoneLabel]

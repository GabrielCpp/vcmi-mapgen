"""SegmentStep's result."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from vcmi_mapgen.core.grid.segment import ZoneLabel
from vcmi_mapgen.core.model import Zone


@dataclass(frozen=True, slots=True)
class Segmentation:
    """Each level's zones and its zone label grid, read ``[y][x]``, -1 on a barrier tile."""

    zones: Mapping[int, Mapping[int, Zone]]
    zone_label: Mapping[int, ZoneLabel]

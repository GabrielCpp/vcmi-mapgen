"""TreasureStep's result."""

from __future__ import annotations

from dataclasses import dataclass, field

from vcmi_mapgen.core.planning.pricing import CutoffPlace


@dataclass
class TreasureResult:
    """Every filled loot zone and island, per level and zone id."""

    places: dict[int, dict[int, CutoffPlace]] = field(default_factory=dict)

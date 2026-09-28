"""TerrainStep's results."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from vcmi_mapgen.core.grid.segment import ZoneLabel
from vcmi_mapgen.core.model import Tile, Zone


@dataclass
class TerrainGrids:
    """Post-despeckle terrain-code grids + tunnel-corridor protect cells — disposable
    analysis VegetationStep/GameplayStep/BorderStep need, never a MapState fact itself:
    MapState's terrain fields are `cells`/`surfs` (the VCMI tile-string form TerrainStep
    derives FROM these grids), not the raw terrain-code grid (see
    vcmi_mapgen/core/model/AGENTS.md)."""

    grids: dict[int, list[list[int]]] = field(default_factory=dict)
    tunnel_protect: frozenset[Tile] = frozenset()


@dataclass(frozen=True, slots=True)
class Segmentation:
    """Each level's zones and its zone label grid, read ``[y][x]``, -1 on a barrier tile."""

    zones: Mapping[int, Mapping[int, Zone]]
    zone_label: Mapping[int, ZoneLabel]

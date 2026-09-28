"""TerrainStep's result."""

from __future__ import annotations

from dataclasses import dataclass, field

from vcmi_mapgen.core.model import Tile


@dataclass
class TerrainGrids:
    """Post-despeckle terrain-code grids + tunnel-corridor protect cells — disposable
    analysis SegmentStep/VegetationStep/GameplayStep/BorderStep need, never a MapState fact itself:
    MapState's terrain fields are `cells`/`surfs` (the VCMI tile-string form TerrainStep
    derives FROM these grids), not the raw terrain-code grid (see
    vcmi_mapgen/core/model/AGENTS.md)."""

    grids: dict[int, list[list[int]]] = field(default_factory=dict)
    tunnel_protect: frozenset[Tile] = frozenset()

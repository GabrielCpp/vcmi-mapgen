"""The terrain model role: what drawing a map's terrain asks of an algorithm, the brief it
hands over and the draw it gets back."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.steps.terrain_gen.result import PlaceMap


@dataclass(frozen=True, slots=True)
class TerrainOptions:
    """The map's brief: its side in tiles, the water style ('topology', 'none', 'normal' or
    'islands'), whether it has an underground, and its player count."""

    size: int = 72
    water_mode: str = "topology"
    subterrain: bool = False
    players: int = 2


@dataclass(frozen=True, slots=True)
class TerrainDraw:
    """The despeckled ``Terrain`` grid of each level, the underground tunnel cells, each
    level's places, and the lines the model reports."""

    grids: Mapping[int, list[list[Terrain]]]
    tunnel_protect: frozenset[Tile]
    places: PlaceMap
    log: tuple[str, ...] = ()


class TerrainModel(Protocol):
    def draw(
        self, catalog: Catalog, priors: Priors, seed: int, options: TerrainOptions
    ) -> TerrainDraw:
        """Every level's terrain and places, the same for the same seed."""
        ...

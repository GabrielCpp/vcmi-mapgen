"""The terrain model role: what drawing a map's terrain asks of an algorithm, the brief it
hands over and the draw it gets back."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.priors.places import PlaceStats
from vcmi_mapgen.core.priors.territories import TerritoryCount, TerritoryStats
from vcmi_mapgen.core.steps.terrain_gen.homes import Homes
from vcmi_mapgen.core.steps.terrain_gen.layout import Land, Layout
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


@dataclass(frozen=True, slots=True)
class FrontDraw:
    """What a territory front hands back: the grown place ``layout``, the ``homes`` on it,
    the territory of each place, the player of each home place (None elsewhere), the corpus
    ``record`` the territory count and floor came from, how many places the front drew and
    the lines it reports."""

    layout: Layout
    homes: Homes
    territory: tuple[int, ...]
    owners: list[int | None]
    record: TerritoryCount
    drawn: int
    log: tuple[str, ...] = ()


class TerritoryFront(Protocol):
    def draw(
        self,
        land: Land,
        priors: tuple[PlaceStats, TerritoryStats],
        planned: int,
        seed: int,
        options: TerrainOptions,
    ) -> FrontDraw:
        """The places on ``land``, the homes and the territory of each place, the same for
        the same seed. ``planned`` is the land count the corpus records are read at."""
        ...

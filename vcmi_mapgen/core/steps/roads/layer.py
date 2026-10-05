"""The road layer role: what laying one level's roads asks of a road algorithm, the level
it hands over and the road tiles it gets back."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol, final

from vcmi_mapgen.core.grid.segment import ZoneLabel
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.model.road import Road
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.planning.entrances import Passages
from vcmi_mapgen.core.priors.places import RoadStats
from vcmi_mapgen.core.reading.borders import AdjacencyKind
from vcmi_mapgen.core.reading.places import PlaceRole


@dataclass(frozen=True, slots=True)
class RoadPlace:
    """One place as the roads read it: its role and its dominant terrain."""

    role: PlaceRole
    dominant: Terrain


@dataclass(frozen=True, slots=True)
class RoadLevel:
    """One level ready for roads. ``walk`` holds the land tiles no blocking cell or gate
    covers. ``label`` is the place label grid read ``[y][x]``, -1 off land. ``kinds`` holds
    the kind of every realised pair ``(a, b)``, ``a < b``, and ``passages`` the planned
    passages across them. ``homes`` holds each player town's place and approach tile in
    player order, ``sites`` each place's important visit tiles, towns first, ``shy`` the
    walkable sprite tiles of the objects no road leads to, and ``surface`` the one road
    surface the whole map carries."""

    walk: frozenset[Tile]
    terrain: Sequence[Sequence[Terrain]]
    label: ZoneLabel
    places: Mapping[int, RoadPlace]
    kinds: Mapping[tuple[int, int], AdjacencyKind]
    passages: Passages
    homes: tuple[tuple[int, Tile], ...] = ()
    sites: Mapping[int, tuple[Tile, ...]] = field(default_factory=dict[int, tuple[Tile, ...]])
    shy: frozenset[Tile] = frozenset()
    surface: Road = Road.DIRT


class RoadLayer(Protocol):
    def lay(self, stats: RoadStats, level: RoadLevel) -> Mapping[Tile, Road]:
        """The road surface of every road tile of ``level``, read against the corpus road
        statistics ``stats`` of its level."""
        ...


@final
class NoRoads:
    """The markov terrain's layer: it lays no road."""

    def lay(self, stats: RoadStats, level: RoadLevel) -> Mapping[Tile, Road]:
        _ = stats, level
        return {}

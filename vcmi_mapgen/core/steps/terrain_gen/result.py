"""TerrainStep's results."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from vcmi_mapgen.core.grid.segment import ZoneLabel
from vcmi_mapgen.core.model import Tile, Zone
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.planning.entrances import Passages
from vcmi_mapgen.core.reading.borders import AdjacencyKind
from vcmi_mapgen.core.reading.places import PlaceRole


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


@dataclass(frozen=True, slots=True)
class PlannedPlace:
    """One place the terrain model laid out: its role, the player it is home to, and its
    dominant terrain, which most of its tiles carry once Paint has graded its bands, grown its
    accents and textured it."""

    role: PlaceRole
    owner: int | None
    dominant: Terrain


@dataclass(frozen=True, slots=True)
class LevelPlaces:
    """One level's places: the label grid read ``[y][x]`` with -1 off land, each place by
    its label, the planned adjacency as pairs ``(a, b)`` with ``a < b``, the tiles of every
    transition band Paint graded, empty when the level was not painted, the kind of every
    realised pair, and the passages across them."""

    label: ZoneLabel
    places: Mapping[int, PlannedPlace]
    adjacency: frozenset[tuple[int, int]]
    bands: frozenset[Tile] = frozenset()
    kinds: Mapping[tuple[int, int], AdjacencyKind] = field(
        default_factory=dict[tuple[int, int], AdjacencyKind]
    )
    passages: Passages = field(default_factory=lambda: Passages({}))

    @property
    def passable(self) -> frozenset[tuple[int, int]]:
        """The realised pairs whose border is not closed."""
        return frozenset(pq for pq, kind in self.kinds.items() if kind != AdjacencyKind.CLOSED)


@dataclass(frozen=True, slots=True)
class PlaceMap:
    """Each level's places, the zones every later step reads."""

    levels: Mapping[int, LevelPlaces]

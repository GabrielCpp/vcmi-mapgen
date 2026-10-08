"""TerrainStep's results."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from vcmi_mapgen.core.grid.segment import ZoneLabel
from vcmi_mapgen.core.model import Tile, Zone
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.planning.entrances import Passages
from vcmi_mapgen.core.reading.borders import AdjacencyKind
from vcmi_mapgen.core.reading.paint import Accent
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
class PlannedDoor:
    """One door the terrain model planned: the zone pair ``(a, b)``, ``a < b``, it crosses,
    the territory and the owner on each side in the same order, and its tile on each side."""

    zones: tuple[int, int]
    territories: tuple[int, int]
    owners: tuple[int | None, int | None]
    tiles: tuple[Tile, Tile]

    def player_side(self) -> int | None:
        """The zone on the side of a player territory, the first when both sides are a
        player's, None between two neutral territories."""
        for zone, owner in zip(self.zones, self.owners, strict=True):
            if owner is not None:
                return zone
        return None


@dataclass(frozen=True, slots=True)
class TerritoryPlan:
    """One level's planned territories: the territory of each zone, the player each
    territory belongs to, None when it is neutral, and every door between two territories.
    Every other border between two territories is walled."""

    zones: Mapping[int, int] = field(default_factory=dict[int, int])
    owners: tuple[int | None, ...] = ()
    doors: tuple[PlannedDoor, ...] = ()

    def zones_of(self, territory: int) -> tuple[int, ...]:
        return tuple(sorted(z for z, t in self.zones.items() if t == territory))


@dataclass(frozen=True, slots=True)
class LevelPlaces:
    """One level's places: the label grid read ``[y][x]`` with -1 off land, each place by
    its label, the planned adjacency as pairs ``(a, b)`` with ``a < b``, the tiles of every
    transition band Paint graded, empty when the level was not painted, the kind of every
    realised pair, the passages across them, and its territories."""

    label: ZoneLabel
    places: Mapping[int, PlannedPlace]
    adjacency: frozenset[tuple[int, int]]
    bands: frozenset[Tile] = frozenset()
    kinds: Mapping[tuple[int, int], AdjacencyKind] = field(
        default_factory=dict[tuple[int, int], AdjacencyKind]
    )
    passages: Passages = field(default_factory=lambda: Passages({}))
    territories: TerritoryPlan = field(default_factory=TerritoryPlan)

    @property
    def passable(self) -> frozenset[tuple[int, int]]:
        """The realised pairs whose border is not closed."""
        return frozenset(pq for pq, kind in self.kinds.items() if kind != AdjacencyKind.CLOSED)


@dataclass(frozen=True, slots=True)
class PlaceMap:
    """Each level's places, the zones every later step reads."""

    levels: Mapping[int, LevelPlaces]


@dataclass(frozen=True, slots=True)
class Accents:
    """Each level's accent patches: the same-terrain components off their place's dominant
    terrain that touch no other place."""

    levels: Mapping[int, tuple[Accent, ...]] = field(default_factory=dict[int, tuple[Accent, ...]])

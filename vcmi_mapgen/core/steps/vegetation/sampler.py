"""The sampler role: what growing a level asks of a vegetation algorithm for one zone, the
brief it hands over and the growth it gets back."""

from collections.abc import Collection, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import Protocol

from vcmi_mapgen.core.model import PlacedObject, Tile
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.planning.web import ZoneRef
from vcmi_mapgen.core.steps.vegetation.model import VegModel

_NO_TILES: frozenset[Tile] = frozenset()

type ZoneGrowth = tuple[list[PlacedObject], set[Tile], AbstractSet[Tile]]


@dataclass(frozen=True, slots=True)
class SampleOptions:
    """One zone's brief: the web kept open, the tiles no vegetation may touch, the rim to
    thicken, the walls that count for connectivity and the level's terrain grid every
    blocking cell must be allowed on. An empty ``ground`` checks no terrain."""

    prot: AbstractSet[Tile] | None = None
    forbid: AbstractSet[Tile] = _NO_TILES
    border: Collection[Tile] = _NO_TILES
    impassable: AbstractSet[Tile] = _NO_TILES
    ground: Sequence[Sequence[Terrain]] = ()


class Sampler(Protocol):
    def sample(self, zone: ZoneRef, model: VegModel, seed: int, opts: SampleOptions) -> ZoneGrowth:
        """One zone's vegetation: the placed objects in row order, the tiles they block and
        the protected web."""
        ...

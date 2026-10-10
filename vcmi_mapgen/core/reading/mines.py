"""The resource mines and the measure of a map their count follows: its land area over every
level and its player count, read the same way on a corpus map and a generated one.

Every map must cover the six basic resource mines. Gold is the deliberate exception: it is
only worth placing when the map holds several towns."""

from collections.abc import Iterable
from dataclasses import dataclass

from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.reading.families import mine_family

BASIC_MINE_RES = ("sawmill", "orePit", "alchemistLab", "sulfurDune", "crystalCavern", "gemPond")

GOLD = "goldMine"

RESOURCE_MINES = (*BASIC_MINE_RES, GOLD)

RESOURCE_FAMILIES = frozenset(mine_family(r) for r in RESOURCE_MINES)


@dataclass(frozen=True, slots=True)
class MapMeasure:
    """A map's land tiles over every level and the players it is made for."""

    land: int
    players: int


def land_area(state: MapState) -> int:
    """The tiles neither water nor rock over every level of ``state``."""
    return sum(t.is_land for grid in state.terrain.values() for row in grid for t in row)


def resource_mines(families: Iterable[str | None]) -> int:
    """How many of ``families`` are resource mine families."""
    return sum(f in RESOURCE_FAMILIES for f in families)

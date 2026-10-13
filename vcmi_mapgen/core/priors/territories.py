"""The corpus territory spread one level of a generated map draws from."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TerritoryCount:
    """One corpus map's level: its player count, its walkable land tiles and its territory
    count."""

    players: int
    land: int
    territories: int


@dataclass(frozen=True, slots=True)
class TerritoryStats:
    """One level's territories pooled over the corpus: the zone count of each player and
    each neutral territory and the door count of each bordering pair. Each corpus map
    keeps its own creature levels of the doors out of a player territory and of the doors
    between neutral ones, so a generated map draws its doors from one map's spread, and its
    own territory count, so a generated map draws its count from the maps nearest it."""

    player_zones: tuple[int, ...] = ()
    neutral_zones: tuple[int, ...] = ()
    pair_doors: tuple[int, ...] = ()
    player_doors_by_map: tuple[tuple[int, ...], ...] = ()
    neutral_doors_by_map: tuple[tuple[int, ...], ...] = ()
    counts_by_map: tuple[TerritoryCount, ...] = ()

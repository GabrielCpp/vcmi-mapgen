"""The corpus territory spread one level of a generated map draws from."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TerritoryStats:
    """One level's territories pooled over the corpus: the zone count of each player and
    each neutral territory, the door count of each bordering pair, and the creature level
    of each door out of a player territory and of each door between neutral ones."""

    player_zones: tuple[int, ...] = ()
    neutral_zones: tuple[int, ...] = ()
    pair_doors: tuple[int, ...] = ()
    player_door_levels: tuple[int, ...] = ()
    neutral_door_levels: tuple[int, ...] = ()

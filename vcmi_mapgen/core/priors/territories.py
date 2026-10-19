"""The corpus territory spread one level of a generated map draws from."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TerritoryCount:
    """One corpus map's level: its player count, its walkable land tiles and its territory
    count, then the tiles of each player's territory, an equal part of one several players
    share, and of all its territories together, and the prizes it holds: its towns and its
    objects worth a mine or more."""

    players: int
    land: int
    territories: int
    homes: tuple[int, ...] = ()
    area: int = 0
    prizes: int = 0

    @property
    def prize_tiles(self) -> float | None:
        """The land tiles per prize, None when the level reads no land or no prize."""
        if self.land <= 0 or self.prizes <= 0:
            return None
        return self.land / self.prizes

    @property
    def home_share(self) -> float | None:
        """The mean player's share of the tiles of all the territories, None when the
        level reads no player territory."""
        if not self.homes or self.area <= 0:
            return None
        return sum(self.homes) / len(self.homes) / self.area


@dataclass(frozen=True, slots=True)
class TerritorySite:
    """One corpus territory placed on the unit square: its centroid ``(x, y)``, its share of
    the map's territory area and its player, None when it is neutral."""

    x: float
    y: float
    share: float
    owner: int | None


@dataclass(frozen=True, slots=True)
class TerritoryPlan:
    """One corpus map's arrangement of territories: the ``sites`` of its territories, each
    held by at most one player, beside the ``record`` of the same map."""

    record: TerritoryCount
    sites: tuple[TerritorySite, ...]


@dataclass(frozen=True, slots=True)
class TerritoryStats:
    """One level's territories pooled over the corpus: the door count of each bordering
    pair. Each corpus map keeps its own creature levels of the doors out of a player
    territory and of the doors between neutral ones, so a generated map draws its doors
    from one map's spread, and its own territory record, so a generated map draws its
    territory count and home budget from the maps nearest it."""

    pair_doors: tuple[int, ...] = ()
    player_doors_by_map: tuple[tuple[int, ...], ...] = ()
    neutral_doors_by_map: tuple[tuple[int, ...], ...] = ()
    counts_by_map: tuple[TerritoryCount, ...] = ()
    plans_by_map: tuple[TerritoryPlan, ...] = ()

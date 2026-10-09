"""The guard level of a crossing between two territories, drawn from the door levels of one
corpus map: those of its doors out of a player territory and those of its doors between
neutral ones. Doors and portals between two territories share it."""

from __future__ import annotations

import random
from dataclasses import dataclass

from vcmi_mapgen.core.priors.territories import TerritoryStats

DEFAULT_DOOR_LEVEL = 3
TOP_LEVEL = 7


@dataclass(frozen=True, slots=True)
class DoorSpread:
    """The door levels one corpus map gives a generated level: those of its doors out of a
    player territory and those of its doors between neutral ones."""

    player: tuple[int, ...] = ()
    neutral: tuple[int, ...] = ()

    @classmethod
    def draw(cls, stats: TerritoryStats, rng: random.Random) -> DoorSpread:
        """The player doors of one corpus map and the neutral doors of one, each drawn
        among the maps that have such doors."""
        player = rng.choice(stats.player_doors_by_map) if stats.player_doors_by_map else ()
        neutral = rng.choice(stats.neutral_doors_by_map) if stats.neutral_doors_by_map else ()
        return cls(player, neutral)


def spread_level(spread: DoorSpread, player: bool, rng: random.Random, cap: int = TOP_LEVEL) -> int:
    """The creature level of a crossing's guard up to ``cap``, drawn from the doors out of a
    player territory when ``player`` holds, from the doors between neutral ones otherwise,
    and ``DEFAULT_DOOR_LEVEL`` within the cap when that spread holds no level it allows."""
    levels = spread.player if player else spread.neutral
    levels = [n for n in levels if 1 <= n <= cap]
    return rng.choice(levels) if levels else min(DEFAULT_DOOR_LEVEL, cap)

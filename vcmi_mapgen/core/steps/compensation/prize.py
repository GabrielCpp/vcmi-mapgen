"""Which players fall behind the bar of value claimed first, the artifact prize each one gets,
and the tiles where that player reaches the prize before every other player."""

import math
from collections.abc import Mapping, Sequence
from typing import cast

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.model.artifact import TIERS, ArtifactTier
from vcmi_mapgen.core.reading.value import ARTIFACT_VALUE

BAR: Mapping[int, float] = {20: 0.46, 40: 0.38}


def deficits(claimed: Mapping[int, Sequence[int]], bar: Mapping[int, float]) -> tuple[int, ...]:
    """Per player, the gold it lacks to reach ``bar`` times the best player's claimed value at
    its worse horizon, zero when it meets the bar at every horizon. ``claimed`` maps each
    horizon of ``bar`` to the value each player claims first within it."""
    rows = [claimed[h] for h in bar]
    players = len(rows[0]) if rows else 0
    return tuple(
        max(
            (max(0, math.ceil(bar[h] * max(claimed[h]) - claimed[h][p])) for h in bar),
            default=0,
        )
        for p in range(players)
    )


def prize_tier(deficit: int) -> ArtifactTier | None:
    """The cheapest artifact tier worth at least ``deficit``, the top tier when none is, and
    None when nothing is lacking."""
    if deficit <= 0:
        return None
    for tier in TIERS:
        if ARTIFACT_VALUE[tier] >= deficit:
            return tier
    return TIERS[-1]


def prize_ground(totals: NDArray[np.int64], player: int, within: int) -> NDArray[np.bool_]:
    """Per tile, whether ``player`` visits it within ``within`` days and strictly before every
    other player. ``totals`` holds one row of days per player, negative where that player never
    reaches the tile."""
    never = np.iinfo(np.int64).max
    days = cast(NDArray[np.int64], np.where(totals < 0, never, totals))
    mine = cast(NDArray[np.int64], days[player])
    rivals = cast(NDArray[np.int64], np.delete(days, player, axis=0).min(axis=0, initial=never))
    return cast(NDArray[np.bool_], (mine != never) & (mine <= within) & (mine < rivals))

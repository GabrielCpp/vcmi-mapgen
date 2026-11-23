"""The towns the players start in."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from vcmi_mapgen.core.model import PlacedObject


def player_towns(
    homes: Mapping[tuple[int, int], PlacedObject],
    player_zids: Sequence[tuple[int, int]],
    moved: Sequence[PlacedObject],
    towns: Mapping[tuple[int, int], Sequence[PlacedObject]],
    players: int,
) -> list[PlacedObject]:
    """Each player's home town, then the towns moved out of a home zone too small for one.

    A spare town tops the list up only when a move failed too.
    """
    out = [homes[k] for k in player_zids if k in homes]
    out += moved
    if not players:
        return out
    spare = [t for zone_towns in towns.values() for t in zone_towns if t not in out]
    out += spare[: max(0, players - len(out))]
    return out[:players]

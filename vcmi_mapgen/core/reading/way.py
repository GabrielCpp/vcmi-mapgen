"""Each player's way out to the rare mines: the rare mines it reaches first, nearest first,
and where the way repeats a resource before it has met every one the map offers. Also the
share of rare mines with another of their resource close by."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import PlacedObject
from vcmi_mapgen.core.reading.effort import EffortMap
from vcmi_mapgen.core.reading.mines import RARE_MINE_RES
from vcmi_mapgen.core.reading.promise import effort_to, mine_resource
from vcmi_mapgen.core.reading.supply import apart, entrance

CLOSE = 10


@dataclass(frozen=True, slots=True)
class PlayerWay:
    """One player's rare mines, nearest first, each with its days and resource."""

    player: int
    mines: tuple[tuple[int, str], ...]

    def repeat(self, offered: Iterable[str]) -> int | None:
        """The place on the way of the first mine that repeats a resource before every
        resource of ``offered`` was met, None when the way meets them all first."""
        left = set(offered)
        seen: set[str] = set()
        for i, (_days, res) in enumerate(self.mines):
            if not left:
                return None
            if res in seen:
                return i
            seen.add(res)
            left.discard(res)
        return None


def rare_mines(catalog: Catalog, objs: Iterable[PlacedObject]) -> list[tuple[str, PlacedObject]]:
    """The rare mines of ``objs``, each with its resource."""
    return [(res, o) for o in objs if (res := mine_resource(catalog, o)) in RARE_MINE_RES]


def player_ways(
    catalog: Catalog, objs: Sequence[PlacedObject], maps: Sequence[EffortMap]
) -> list[PlayerWay]:
    """Per player, in the order of ``maps``, the rare mines it reaches before every other
    player, the lower player first on a tie. A mine no player reaches is on no way."""
    ways: list[list[tuple[int, str]]] = [[] for _ in maps]
    for res, o in rare_mines(catalog, objs):
        priced = [(d, p) for p, em in enumerate(maps) if (d := effort_to(em, [o])) is not None]
        if priced:
            days, player = min(priced)
            ways[player].append((days, res))
    return [PlayerWay(p, tuple(sorted(w))) for p, w in enumerate(ways)]


def close_share(catalog: Catalog, objs: Iterable[PlacedObject], within: int = CLOSE) -> float:
    """The share of rare mines with another mine of their resource on their level within
    ``within`` tiles, entrance to entrance. Zero on a map with no rare mine."""
    mines = [(res, o.level, entrance(o)) for res, o in rare_mines(catalog, objs)]
    close = sum(
        any(
            j != i and r == res and lv == level and apart(t, tile) <= within
            for j, (r, lv, t) in enumerate(mines)
        )
        for i, (res, level, tile) in enumerate(mines)
    )
    return close / len(mines) if mines else 0.0

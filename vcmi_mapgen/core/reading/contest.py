"""Where the players fight over a tile: the days between the first player to reach it and that
player's nearest enemy, and the far floor, the days from every home inside which no gold mine
stands. Also each gold mine's days from the nearest home and its contest."""

from __future__ import annotations

import itertools
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import cast

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import PlacedObject
from vcmi_mapgen.core.reading.effort import EffortMap
from vcmi_mapgen.core.reading.mines import GOLD
from vcmi_mapgen.core.reading.promise import effort_to, mine_resource

FAR_FLOOR = 8
CONTEST = 3
OPEN = int(np.iinfo(np.int64).max)

type Codes = NDArray[np.int64]
type Pairs = Sequence[tuple[int, int]]


def enemy_pairs(players: int, teams: Sequence[int] = ()) -> list[tuple[int, int]]:
    """Every pair of players on different teams. Without ``teams`` every other player is
    an enemy."""
    team = list(teams) or list(range(players))
    return [(a, b) for a, b in itertools.combinations(range(players), 2) if team[a] != team[b]]


def _enemy_of(players: int, enemies: Pairs) -> NDArray[np.bool_]:
    out = np.zeros((players, players), dtype=np.bool_)
    for a, b in enemies:
        if a < players and b < players:
            out[a, b] = out[b, a] = True
    return out


def soonest(days: Codes) -> Codes:
    """Per row of ``days``, one column per player and negative where the player never
    arrives, the fewest days over the players, OPEN where none arrives."""
    return cast(Codes, np.where(days >= 0, days, OPEN).min(axis=1, initial=OPEN))


def contest(days: Codes, enemies: Pairs) -> Codes:
    """Per row of ``days`` as `soonest` reads them, the days between the first player to
    arrive, the lowest on a tie, and that player's nearest enemy among ``enemies``. OPEN
    where no player arrives or no enemy of the first does."""
    n, players = days.shape
    if players == 0:
        return np.full(n, OPEN, dtype=np.int64)
    at = np.where(days >= 0, days, OPEN)
    first = cast(NDArray[np.intp], at.argmin(axis=1))
    lead = cast(Codes, at[np.arange(n), first])
    rival = cast(Codes, np.where(_enemy_of(players, enemies)[first], at, OPEN).min(axis=1))
    gone = cast(NDArray[np.bool_], (lead == OPEN) | (rival == OPEN))
    return np.where(gone, OPEN, rival - lead)


def row(days: Sequence[int | None]) -> Codes:
    """One tile's days per player as a single row, -1 where the player never arrives."""
    return np.array([-1 if d is None else d for d in days], dtype=np.int64).reshape(1, -1)


def _known(value: int) -> int | None:
    return None if value == OPEN else value


@dataclass(frozen=True, slots=True)
class GoldMine:
    """One gold mine, its days from the nearest home and its contest, each None when no
    player arrives or, for the contest, no enemy of the first does."""

    obj: PlacedObject
    days: int | None
    contest: int | None

    def misses(self, bounded: bool) -> list[str]:
        """Why the mine breaks the far floor or, when ``bounded``, the contest bound."""
        where = f"gold mine at {(self.obj.x, self.obj.y)} level {self.obj.level}"
        out: list[str] = []
        if self.days is not None and self.days <= FAR_FLOOR:
            out.append(f"{where}: {self.days} days from a home")
        if bounded and (self.contest is None or self.contest > CONTEST):
            gap = "no enemy arrives" if self.contest is None else f"contest {self.contest} days"
            out.append(f"{where}: {gap}")
        return out


def gold_mines(
    catalog: Catalog, objs: Iterable[PlacedObject], maps: Sequence[EffortMap], enemies: Pairs
) -> list[GoldMine]:
    """Every gold mine of ``objs`` with its days from the nearest home and its contest, the
    players in the order of ``maps``."""
    out: list[GoldMine] = []
    for o in objs:
        if mine_resource(catalog, o) == GOLD:
            days = row([effort_to(em, [o]) for em in maps])
            first = soonest(days).item(0)
            gap = contest(days, enemies).item(0)
            out.append(GoldMine(o, _known(first), _known(gap)))
    return out

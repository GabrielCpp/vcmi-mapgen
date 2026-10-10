"""Where a gold mine may stand: past the far floor from every home through its own guard and,
where the players have enemies, on land the first player to reach it holds by at most CONTEST
days over its nearest enemy. The spots it admits rank by that contest, the closest first.
Without an enemy they rank by days from the nearest home, the farthest first. Where no
admitted spot takes a gold mine, the loose rule admits the far spots past the contest bound
instead."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.placement.site import MINE_GUARD_LVL
from vcmi_mapgen.core.reading.contest import (
    CONTEST,
    FAR_FLOOR,
    OPEN,
    Codes,
    Pairs,
    contest,
    row,
    soonest,
)
from vcmi_mapgen.core.reading.mines import GOLD


@dataclass(frozen=True, slots=True)
class GoldSpot:
    """The gold rule over the players' days to each tile, ``enemies`` the pairs of enemy
    players and ``guard`` the days the mine's own guard adds."""

    enemies: Pairs
    guard: int = 0
    floor: int = FAR_FLOOR

    @classmethod
    def of(cls, enemies: Pairs, toll: Sequence[int]) -> GoldSpot:
        """The gold rule behind the guard level every gold mine stands behind, priced by
        ``toll``."""
        return cls(enemies, toll[min(MINE_GUARD_LVL[GOLD], len(toll) - 1)])

    def rank(self, days: Codes, loose: bool = False) -> tuple[NDArray[np.bool_], Codes]:
        """Per row of ``days``, one column per player and negative where the player never
        arrives, whether a gold mine may stand there and its rank, the lower the better. The
        ``loose`` rule admits only the far rows the strict rule leaves out."""
        first = soonest(days)
        far = cast(NDArray[np.bool_], (first != OPEN) & (first + self.guard > self.floor))
        if not self.enemies:
            return far & (not loose), np.where(far, -first, 0)
        gap = contest(days, self.enemies)
        held = gap <= CONTEST
        return far & (held != loose), gap

    def admits(self, days: Sequence[int | None]) -> bool:
        """Whether a gold mine may stand where the players reach it in ``days``, None for a
        player who never does."""
        ok, _key = self.rank(row(days))
        return ok.item(0)

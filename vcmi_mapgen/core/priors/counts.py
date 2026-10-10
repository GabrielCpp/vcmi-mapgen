"""The corpus curves of an object count over a map's land area and player count: one for the
resource mines and one for the towns."""

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CountCurve:
    """``exp(intercept) * land ** land_exp * players ** players_exp``, fitted in log space
    over the corpus maps, the intercept corrected for the bias of the log mean."""

    intercept: float
    land_exp: float
    players_exp: float

    def expected(self, land: int, players: int) -> float:
        """The expected count on a map of ``land`` tiles and ``players`` players."""
        if land <= 0:
            return 0.0
        log = self.intercept + self.land_exp * math.log(land)
        return math.exp(log + self.players_exp * math.log(max(players, 1)))


MINE_CURVE = CountCurve(-1.39, 0.49, 0.51)
TOWN_CURVE = CountCurve(-2.43, 0.41, 0.68)

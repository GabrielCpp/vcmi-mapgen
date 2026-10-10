"""The corpus curve of the resource mine count over a map's land area and player count."""

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MineCurve:
    """``exp(intercept) * land ** land_exp * players ** players_exp``, fitted in log space
    over the corpus maps, the intercept corrected for the bias of the log mean."""

    intercept: float = -1.39
    land_exp: float = 0.49
    players_exp: float = 0.51

    def expected(self, land: int, players: int) -> float:
        """The expected resource mines on a map of ``land`` tiles and ``players`` players."""
        if land <= 0:
            return 0.0
        log = self.intercept + self.land_exp * math.log(land)
        return math.exp(log + self.players_exp * math.log(max(players, 1)))

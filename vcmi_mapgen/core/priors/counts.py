"""The corpus curves of an object count over a map's land area and player count: one for the
towns, one for the resource mines, and one per gameplay family beside the power its efforts
from home stretch by with the land and the share of its objects at each guard level. Only the
town curve grows with the player count."""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field


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


MINE_CURVE = CountCurve(-1.69, 0.61, 0.0)
TOWN_CURVE = CountCurve(-2.43, 0.41, 0.68)


@dataclass(frozen=True, slots=True)
class FamilyFit:
    """One gameplay family's corpus fit: its count curve, the power of the land ratio its
    efforts from home stretch by, and its guard record, the share of its objects whose own
    guard is of each level from 0, unguarded, up."""

    count: CountCurve
    stretch: float = 0.0
    guards: tuple[float, ...] = ()


def _no_fits() -> Mapping[str, FamilyFit]:
    return {}


@dataclass(frozen=True, slots=True)
class FamilyCurves:
    """The corpus fit of each gameplay family, read against ``land_ref``, the corpus median
    land. An empty one leaves every family at the corpus rate per tile and its corpus
    efforts as they are."""

    land_ref: int = 0
    fits: Mapping[str, FamilyFit] = field(default_factory=_no_fits)

    def curve(self, family: str) -> CountCurve | None:
        """The count curve of ``family``, None when the corpus fit none."""
        fit = self.fits.get(family)
        return fit.count if fit is not None else None

    def guards(self, family: str) -> tuple[float, ...]:
        """The guard record of ``family``, empty when the corpus fit none."""
        fit = self.fits.get(family)
        return fit.guards if fit is not None else ()

    def factor(self, family: str, land: int) -> float:
        """What a corpus effort of ``family`` scales by on a map of ``land`` tiles."""
        fit = self.fits.get(family)
        if fit is None or land <= 0 or self.land_ref <= 0:
            return 1.0
        return math.pow(land / self.land_ref, fit.stretch)

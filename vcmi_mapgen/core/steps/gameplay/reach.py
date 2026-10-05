"""What each player reaches of each family within each effort band, and how far an object
would push the players apart. A player who reaches an object in band ``b`` holds it in every
band from ``b`` on, so the count per band is the count within that effort."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from vcmi_mapgen.core.priors.effort import BANDS

type Bands = tuple[int | None, ...]

SLACK = 1


@dataclass(slots=True)
class Reach:
    """Per family, the objects each player reaches in each band."""

    players: int
    held: Counter[tuple[str, int, int]] = field(default_factory=Counter[tuple[str, int, int]])
    _cost: dict[tuple[str, Bands, int], int] = field(
        default_factory=dict[tuple[str, Bands, int], int]
    )

    def clear(self) -> None:
        self.held.clear()
        self._cost.clear()

    def add(self, family: str, bands: Bands) -> None:
        """Count one object of ``family`` that each player reaches in ``bands``, None for a
        player who never does."""
        for p, b in enumerate(bands):
            if b is not None:
                self.held[family, p, b] += 1
        self._cost.clear()

    def within(self, family: str, player: int) -> list[int]:
        """The objects of ``family`` ``player`` reaches within each band 1..BANDS."""
        out: list[int] = []
        total = 0
        for b in range(1, BANDS + 1):
            total += self.held[family, player, b]
            out.append(total)
        return out

    def cost(self, family: str, bands: Bands, slack: int) -> int:
        """How much further one more object of ``family`` at ``bands`` would spread the
        players than they stand now. The spread sums over the bands the gap between the
        players who reach the most and the fewest within each, beyond ``slack``."""
        key = (family, bands, slack)
        if key not in self._cost:
            now = self._spread(family, (), slack)
            self._cost[key] = self._spread(family, bands, slack) - now
        return self._cost[key]

    def _spread(self, family: str, bands: Bands, slack: int) -> int:
        if self.players < 2:
            return 0
        rows = [self.within(family, p) for p in range(self.players)]
        for p, b in enumerate(bands[: self.players]):
            if b is not None:
                rows[p] = [n + int(i + 1 >= b) for i, n in enumerate(rows[p])]
        return sum(max(0, _gap([r[i] for r in rows]) - slack) for i in range(BANDS))


def _gap(counts: Sequence[int]) -> int:
    return max(counts) - min(counts)

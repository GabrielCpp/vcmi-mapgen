"""The guard a gameplay object stands behind, drawn from its family's corpus record: unguarded
or the level of its own guard, as often as the corpus shows each."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from vcmi_mapgen.core.priors.counts import FamilyCurves


@dataclass(frozen=True, slots=True)
class GuardDraw:
    """Draws each object's own guard level from the guard record of its family in ``curves``,
    0 for no guard. A family the corpus records nothing for stands unguarded, and no draw goes
    past ``top``."""

    curves: FamilyCurves = field(default_factory=FamilyCurves)
    top: int = 0

    def draw(self, rng: random.Random, family: str) -> int:
        """The level of the guard one object of ``family`` stands behind."""
        record = self.curves.guards(family)
        if not record or self.top <= 0:
            return 0
        level = rng.choices(range(len(record)), weights=record)[0]
        return min(level, self.top)

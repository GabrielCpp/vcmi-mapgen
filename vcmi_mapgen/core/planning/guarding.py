"""The guard in front of each prize in a cut-off place: its level drawn from the corpus
spread of random-guard levels at the place's hop from home, never from the prize's worth."""

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from vcmi_mapgen.core.planning.content import LEVEL_MAX, LEVEL_MIN, ContentPlan, hop_bin
from vcmi_mapgen.core.priors.places import PlaceContent, PlaceStats

EVERY_LEVEL = tuple(range(LEVEL_MIN, LEVEL_MAX + 1))


@dataclass(frozen=True, slots=True)
class GuardReading:
    """The corpus random-guard levels of one level, pooled by hop bin and over the whole
    level."""

    by_hop: Mapping[int, tuple[int, ...]] = field(default_factory=dict[int, tuple[int, ...]])
    every: tuple[int, ...] = ()

    @staticmethod
    def of(rows: Sequence[PlaceContent]) -> "GuardReading":
        by_hop: dict[int, list[int]] = {}
        for row in rows:
            by_hop.setdefault(hop_bin(row.hop), []).extend(row.guards)
        every = tuple(sorted(level for row in rows for level in row.guards))
        return GuardReading({h: tuple(sorted(v)) for h, v in by_hop.items() if v}, every)

    def spread(self, hop: int | None) -> tuple[int, ...]:
        """The guard levels at ``hop``, the whole level's when the hop is unknown or the
        corpus has none there, and every random monster level when the corpus has none."""
        found = () if hop is None else self.by_hop.get(hop_bin(hop), ())
        return found or self.every or EVERY_LEVEL


@dataclass(frozen=True, slots=True)
class PrizeGuard:
    """One level's guard reading and the hop of each planned place on it."""

    reading: GuardReading = field(default_factory=GuardReading)
    hops: Mapping[int, int] = field(default_factory=dict[int, int])

    def level(self, rng: random.Random, zid: int) -> int:
        """The level of the guard in front of zone ``zid``'s prize. One draw of ``rng``."""
        return rng.choice(self.reading.spread(self.hops.get(zid)))


def prize_guard(stats: Mapping[int, PlaceStats], plan: ContentPlan, level: int) -> PrizeGuard:
    """The prize guard of ``level``, read off its corpus place statistics and the planned
    hop of each place."""
    level_stats = stats.get(level)
    reading = GuardReading.of(level_stats.content) if level_stats is not None else GuardReading()
    hops = {zid: intent.hop for (lvl, zid), intent in plan.intents.items() if lvl == level}
    return PrizeGuard(reading, hops)

"""The corpus gate estimator the gate pairs draw from."""

import random
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GateStats:
    """Corpus gate estimator: the gate counts of two-level corpus maps grouped by map width,
    and the closest-pair gate gap as a fraction of map width."""

    counts_by_size: Mapping[int, tuple[int, ...]]
    min_gap_frac: float
    n_maps: int

    def draw_count(self, size: int, rng: random.Random) -> int:
        """A gate count drawn from corpus maps of the nearest width."""
        if not self.counts_by_size:
            return 1
        width = min(self.counts_by_size, key=lambda w: (abs(w - size), w))
        return rng.choice(self.counts_by_size[width])

    def min_gap(self, size: int) -> float:
        return self.min_gap_frac * size

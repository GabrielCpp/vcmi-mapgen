"""The corpus spread of each reading and the rule that decides whether a candidate model
replaces the default one (map-math 8)."""

from __future__ import annotations

import statistics
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Spread:
    """The quartiles of one reading over ``n`` maps."""

    n: int
    q1: float
    median: float
    q3: float

    @property
    def iqr(self) -> float:
        return self.q3 - self.q1

    @classmethod
    def of(cls, values: Sequence[float]) -> Spread | None:
        if not values:
            return None
        if len(values) == 1:
            return cls(1, values[0], values[0], values[0])
        q1, median, q3 = statistics.quantiles(values, n=4, method="inclusive")
        return cls(len(values), q1, median, q3)


@dataclass(frozen=True, slots=True)
class Comparison:
    """One reading compared: the corpus spread and each model's median distance to the
    corpus median."""

    reading: str
    corpus: Spread
    candidate: float
    baseline: float

    @property
    def candidate_gap(self) -> float:
        return abs(self.candidate - self.corpus.median)

    @property
    def baseline_gap(self) -> float:
        return abs(self.baseline - self.corpus.median)

    @property
    def closer(self) -> bool:
        return self.candidate_gap < self.baseline_gap

    @property
    def blocks(self) -> bool:
        return self.candidate_gap - self.baseline_gap > self.corpus.iqr


@dataclass(frozen=True, slots=True)
class Verdict:
    """The candidate replaces the baseline when it sits closer to the corpus median on a
    strict majority of the compared readings and no reading is worse than the baseline's
    by more than the corpus interquartile range."""

    comparisons: tuple[Comparison, ...]

    @property
    def closer(self) -> tuple[str, ...]:
        return tuple(c.reading for c in self.comparisons if c.closer)

    @property
    def blockers(self) -> tuple[str, ...]:
        return tuple(c.reading for c in self.comparisons if c.blocks)

    @property
    def switch(self) -> bool:
        return 2 * len(self.closer) > len(self.comparisons) and not self.blockers


def columns(vectors: Sequence[Mapping[str, float]]) -> dict[str, list[float]]:
    """Each reading's values over ``vectors``, in first-seen reading order."""
    out: dict[str, list[float]] = {}
    for vector in vectors:
        for key, value in vector.items():
            out.setdefault(key, []).append(value)
    return out


def decide(
    corpus: Mapping[str, Sequence[float]],
    candidate: Mapping[str, Sequence[float]],
    baseline: Mapping[str, Sequence[float]],
    skip: Collection[str] = (),
) -> Verdict:
    """Compare the candidate and the baseline on every reading all three sides carry,
    leaving out ``skip``."""
    comparisons: list[Comparison] = []
    for reading, values in corpus.items():
        spread = Spread.of(values)
        if reading in skip or spread is None:
            continue
        if not candidate.get(reading) or not baseline.get(reading):
            continue
        comparisons.append(
            Comparison(
                reading,
                spread,
                statistics.median(candidate[reading]),
                statistics.median(baseline[reading]),
            )
        )
    return Verdict(tuple(comparisons))

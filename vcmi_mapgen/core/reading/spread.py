"""The corpus spread of each reading (map-math 8)."""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Spread:
    """The quartiles of one reading over ``n`` maps."""

    n: int
    q1: float
    median: float
    q3: float

    @classmethod
    def of(cls, values: Sequence[float]) -> Spread | None:
        if not values:
            return None
        if len(values) == 1:
            return cls(1, values[0], values[0], values[0])
        q1, median, q3 = statistics.quantiles(values, n=4, method="inclusive")
        return cls(len(values), q1, median, q3)


def columns(vectors: Sequence[Mapping[str, float]]) -> dict[str, list[float]]:
    """Each reading's values over ``vectors``, in first-seen reading order."""
    out: dict[str, list[float]] = {}
    for vector in vectors:
        for key, value in vector.items():
            out.setdefault(key, []).append(value)
    return out

"""The corpus spread of each reading (map-math 8)."""

from __future__ import annotations

import collections
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

MIN_MAPS = 5


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


def nearest_players(counts: Sequence[int], players: int, minimum: int = MIN_MAPS) -> list[int]:
    """The player counts of the corpus maps a ``players`` map reads against, given each
    corpus map's player count in ``counts``. The counts join in order of their distance from
    ``players``, the smaller first on a tie, until their maps number ``minimum`` or every
    count is in."""
    tally = collections.Counter(counts)
    chosen: list[int] = []
    for count in sorted(tally, key=lambda p: (abs(p - players), p)):
        if sum(tally[p] for p in chosen) >= minimum:
            break
        chosen.append(count)
    return sorted(chosen)


@dataclass(frozen=True, slots=True)
class Column:
    """One reading's corpus values over the maps whose player count is in ``players``."""

    players: tuple[int, ...]
    values: tuple[float, ...]


def nearest_columns(
    maps: Sequence[tuple[int, Mapping[str, float]]], players: int, minimum: int = MIN_MAPS
) -> dict[str, Column]:
    """Each reading's values over the corpus ``maps``, each a player count and a reading
    vector, in first-seen reading order. A reading keeps the maps of the player counts
    ``nearest_players`` picks among the maps that read it."""
    pairs: dict[str, list[tuple[int, float]]] = {}
    for count, vector in maps:
        for key, value in vector.items():
            pairs.setdefault(key, []).append((count, value))
    out: dict[str, Column] = {}
    for key, read in pairs.items():
        chosen = nearest_players([c for c, _v in read], players, minimum)
        out[key] = Column(tuple(chosen), tuple(v for c, v in read if c in chosen))
    return out

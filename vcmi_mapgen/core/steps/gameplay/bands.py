"""Which effort band each gameplay object serves. A family's count splits over the bands by
the corpus effort of the family, map-wide, and each object gets a target in days drawn from
the corpus inside its band. No object serves a player: the reach gate keeps the players
even."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.priors.effort import BANDS
from vcmi_mapgen.core.reading.families import FAR_DAYS, family_purpose
from vcmi_mapgen.core.reading.repeats import Kind


@dataclass(frozen=True, slots=True)
class Slot:
    """One object to place: its family, the player and band it serves, its target effort in
    days, and the kind the roster drew for it. A map without players leaves the player, band
    and target None, and a slot the roster leaves out has no kind."""

    family: str
    player: int | None = None
    band: int | None = None
    target: int | None = None
    kind: Kind | None = None


def stretched(days: Sequence[int], factor: float) -> tuple[int, ...]:
    """The count per day ``days`` with every day scaled by ``factor``, rounded to a day and
    capped at FAR_DAYS, so a map larger than the corpus median asks for its efforts further
    from home."""
    out = [0] * (FAR_DAYS + 1)
    for d, n in enumerate(days):
        out[min(round(d * factor), FAR_DAYS)] += n
    return tuple(out)


def band_shares(days: Sequence[int], band_of: Callable[[int], int]) -> list[float]:
    """The share of each band 1..BANDS among ``days``, a count per day. All of it goes to
    the first band when ``days`` is empty."""
    got = [0.0] * BANDS
    for d, n in enumerate(days):
        got[band_of(d) - 1] += n
    total = sum(got)
    if total <= 0:
        return [float(b == 1) for b in range(1, BANDS + 1)]
    return [g / total for g in got]


def band_sequence(shares: Sequence[float], n: int) -> list[int]:
    """The bands of ``n`` objects, each next one going to the band furthest behind its
    share, so the first k of the list split k objects the same way for every k."""
    got = [0] * len(shares)
    out: list[int] = []
    for k in range(1, n + 1):
        b = max(range(len(shares)), key=lambda i: (shares[i] * k - got[i], -i))
        got[b] += 1
        out.append(b + 1)
    return out


def _target(
    rng: random.Random, days: Sequence[int], band: int, band_of: Callable[[int], int]
) -> int:
    inside = [d for d in range(FAR_DAYS + 1) if band_of(d) == band]
    weights = [days[d] if d < len(days) else 0 for d in inside]
    if sum(weights) <= 0:
        return inside[len(inside) // 2]
    return rng.choices(inside, weights=weights)[0]


@dataclass(frozen=True, slots=True)
class BandPlan:
    """The corpus effort per family, the band rule and the player count, to plan each
    family's slots."""

    corpus: Mapping[str, Sequence[int]]
    band_of: Callable[[int], int]
    players: int
    rng: random.Random

    def shared(self, family: str, n: int, standing: Sequence[int | None]) -> list[Slot]:
        """The slots of the ``n`` objects of ``family`` still to place, serving no player, once
        the objects ``standing`` count against the plan, each at its band or the nearest one
        left. One no player reaches counts against the furthest band left."""
        if self.players <= 0:
            return [Slot(family)] * max(0, n - len(standing))
        days = self.corpus.get(family, ())
        left = Counter(band_sequence(band_shares(days, self.band_of), n))
        for band in standing:
            near = sorted((abs(b - (band or BANDS)), -b) for b, k in left.items() if k > 0)
            if near:
                left[-near[0][1]] -= 1
        return [
            Slot(family, None, b, self.target(days, b))
            for b, k in sorted(left.items())
            for _ in range(k)
        ]

    def target(self, days: Sequence[int], band: int) -> int:
        """A target in days inside ``band``, drawn by the corpus count per day ``days``."""
        return _target(self.rng, days, band, self.band_of)


def slot_order(slots: Sequence[Slot], ranks: Sequence[str]) -> list[Slot]:
    """The slots in placing order: by purpose rank, then the far bands first, then one slot
    per family and player in turn."""
    seen: Counter[tuple[str, int | None, int | None]] = Counter()
    keyed: list[tuple[tuple[int, int, int, int, int], Slot]] = []
    families = sorted({s.family for s in slots})
    for s in slots:
        turn = seen[s.family, s.player, s.band]
        seen[s.family, s.player, s.band] += 1
        rank = ranks.index(family_purpose(s.family))
        key = (rank, -(s.band or 0), turn, families.index(s.family), s.player or 0)
        keyed.append((key, s))
    return [s for _k, s in sorted(keyed, key=lambda ks: ks[0])]

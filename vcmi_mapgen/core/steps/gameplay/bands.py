"""Which player and effort band each gameplay object serves. A family's count splits evenly
over the players, and each player's share splits over the bands by the corpus effort of the
family, so per family and band no player holds two more than another. Each object gets a
target in days drawn from the corpus inside its band."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.priors.effort import BANDS
from vcmi_mapgen.core.reading.families import FAR_DAYS, family_purpose

type Cell = tuple[int, int]


@dataclass(frozen=True, slots=True)
class Slot:
    """One object to place: its family, the player and band it serves, and its target effort
    in days. A map without players leaves the three None."""

    family: str
    player: int | None = None
    band: int | None = None
    target: int | None = None


def player_split(n: int, players: int, start: int) -> list[int]:
    """``n`` split evenly over ``players``, the remainder going to the players from
    ``start`` on."""
    base, rest = divmod(n, players)
    return [base + int((p - start) % players < rest) for p in range(players)]


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


def _take(cells: Counter[Cell], cell: Cell | None) -> None:
    if cell is None:
        left = Counter[int]()
        for (p, _b), n in cells.items():
            left[p] += n
        if not left:
            return
        player = min(left, key=lambda p: (-left[p], p))
        band = BANDS
    else:
        player, band = cell
    near = sorted((abs(b - band), b) for (p, b), n in cells.items() if p == player and n > 0)
    if near:
        cells[player, near[0][1]] -= 1


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
    """The corpus effort per family, the band rule and the players, to plan each family's
    slots."""

    corpus: Mapping[str, Sequence[int]]
    band_of: Callable[[int], int]
    players: int
    rng: random.Random

    def slots(self, family: str, n: int, standing: Sequence[Cell | None], start: int) -> list[Slot]:
        """The slots of the ``n`` objects of ``family`` still to place once the objects
        ``standing`` count against the plan, each at its (player, band) cell or the nearest
        band of that player. One no player reaches counts against the player with the most
        left."""
        players = self.players
        if players <= 0:
            return [Slot(family)] * max(0, n - len(standing))
        days = self.corpus.get(family, ())
        shares = band_shares(days, self.band_of)
        cells: Counter[Cell] = Counter()
        for p, count in enumerate(player_split(n, players, start)):
            cells.update((p, b) for b in band_sequence(shares, count))
        for cell in standing:
            _take(cells, cell)
        return [
            Slot(family, p, b, _target(self.rng, days, b, self.band_of))
            for (p, b), k in sorted(cells.items())
            for _ in range(k)
        ]


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

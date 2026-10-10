"""Each player's rare mines dealt in turn along its way out. The rare families plan together:
each family's count splits evenly over the players, each player's rare mines share one set
of bands and target days from the pooled corpus effort of the rare families, and each slot,
nearest target first, takes the rare resource its player has not met yet, then the one
furthest behind its share. A rare mine already standing counts toward its player's share
and keeps its place on the way."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import zip_longest

from vcmi_mapgen.core.model import PlacedObject, Tile
from vcmi_mapgen.core.priors.effort import BANDS
from vcmi_mapgen.core.reading.supply import apart
from vcmi_mapgen.core.reading.way import CLOSE, PlayerWay
from vcmi_mapgen.core.steps.gameplay.bands import (
    BandPlan,
    Slot,
    band_sequence,
    band_shares,
    player_split,
)

type Visit = tuple[int, int] | None
type Key = tuple[int, int, int]

SLACK = 1
MARGIN = 2
type BandOf = Callable[[int], int]


def resource_turn(
    shares: Mapping[str, int],
    got: Mapping[str, int],
    k: int,
    rest: Sequence[tuple[int, str | None]],
) -> str | None:
    """The family of the ``k``-th mine of a way, once the mines ``got`` were dealt and with
    the stops ``rest`` still ahead on it. A family's share counts its standing mines ahead.
    One not met yet first, the one whose next standing mine ahead comes last or never, then
    the one furthest behind its share, the earlier family of ``shares`` on a tie. None when
    every share is held."""
    ahead = _ahead(rest)
    later = Counter(f for _d, f in rest if f is not None)
    total = sum(shares.values())
    left = [f for f in shares if got.get(f, 0) + later[f] < shares[f]]
    if not left:
        return None
    never = 1 + max(ahead.values(), default=0)
    return max(
        left,
        key=lambda f: (
            got.get(f, 0) == 0,
            ahead.get(f, never),
            shares[f] * k / total - got.get(f, 0),
        ),
    )


def _take(cells: Counter[int], band: int) -> None:
    near = sorted((abs(b - band), b) for b, n in cells.items() if n > 0)
    if near:
        cells[near[0][1]] -= 1


@dataclass(frozen=True, slots=True)
class Way:
    """One player's share of each rare family, its band cells still open, and its way so far:
    the standing mines and the open slots as (days, family), None for an open slot."""

    shares: dict[str, int]
    cells: Counter[int]
    stops: list[tuple[int, str | None]]
    off: Counter[str]

    def deal(self, player: int, band_of: BandOf) -> list[Slot]:
        """The open slots in target order, each with the family its turn gives."""
        shares = {f: n - self.off[f] for f, n in self.shares.items()}
        got: Counter[str] = Counter()
        out: list[Slot] = []
        stops = sorted(self.stops, key=lambda s: (s[0], s[1] is None))
        for k, (day, family) in enumerate(stops, 1):
            f = family if family is not None else resource_turn(shares, got, k, stops[k:])
            if f is None:
                continue
            if family is None:
                out.append(Slot(f, player, band_of(day), day))
            got[f] += 1
        return out


def _ahead(stops: Sequence[tuple[int, str | None]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for day, family in stops:
        if family is not None and family not in out:
            out[family] = day
    return out


def rare_slots(
    plan: BandPlan,
    quota: Mapping[str, int],
    standing: Mapping[str, Sequence[Visit]],
    starts: Mapping[str, int],
) -> list[Slot]:
    """The slots of the rare families of ``quota`` still to place, once the mines
    ``standing`` count against their players. A standing mine no player reaches counts
    against the player with the most of its family left, off the way. Each family's count
    then splits over the players so each holds at least its standing mines, the rest going
    to the players with the fewest, from its entry in ``starts`` on."""
    players = plan.players
    families = list(quota)
    if players <= 0:
        return [
            Slot(f) for f in families for _ in range(max(0, quota[f] - len(standing.get(f, ()))))
        ]
    split = {f: player_split(quota[f], players, starts.get(f, 0)) for f in families}
    stops: list[list[tuple[int, str | None]]] = [[] for _ in range(players)]
    off: list[Counter[str]] = [Counter() for _ in range(players)]
    for f in families:
        for visit in standing.get(f, ()):
            if visit is None:
                p = max(range(players), key=lambda i: (split[f][i] - off[i][f], -i))
                off[p][f] += 1
            else:
                stops[visit[0]].append((visit[1], f))
    shares = {f: fill(_held(f, stops, off), quota[f], starts.get(f, 0)) for f in families}
    pooled = [sum(c) for c in zip_longest(*(plan.corpus.get(f, ()) for f in families), fillvalue=0)]
    bands = band_shares(pooled, plan.band_of)
    out: list[Slot] = []
    for p in range(players):
        way = Way({f: shares[f][p] for f in families}, Counter(), stops[p], off[p])
        way.cells.update(band_sequence(bands, sum(way.shares.values())))
        for day, _f in way.stops:
            _take(way.cells, plan.band_of(day))
        for _ in range(way.off.total()):
            _take(way.cells, BANDS)
        for b, k in sorted(way.cells.items()):
            way.stops.extend((plan.target(pooled, b), None) for _ in range(k))
        out += way.deal(p, plan.band_of)
    return out


def _held(
    family: str, stops: Sequence[Sequence[tuple[int, str | None]]], off: Sequence[Counter[str]]
) -> list[int]:
    return [off[p][family] + sum(f == family for _d, f in s) for p, s in enumerate(stops)]


def fill(held: Sequence[int], n: int, start: int) -> list[int]:
    """``n`` split over the players so each holds at least its ``held``, each one left going
    to the player with the fewest, the first from ``start`` on on a tie."""
    players = len(held)
    shares = list(held)
    for _ in range(n - sum(held)):
        p = min(range(players), key=lambda i: (shares[i], (i - start) % players))
        shares[p] += 1
    return shares


def near(days: Sequence[int | None]) -> tuple[tuple[int, int], ...]:
    """The players who reach a tile within SLACK days of the first, nearest first, each with
    its days, the lower player first on a tie."""
    found = sorted((d, p) for p, d in enumerate(days) if d is not None)
    return tuple((p, d) for d, p in found if d <= found[0][0] + SLACK)


@dataclass(frozen=True, slots=True)
class Stop:
    """A rare mine on the ways: its family, the players who reach it within SLACK days of
    the first with their days, nearest first, and its level and entrance tile."""

    family: str
    reach: tuple[tuple[int, int], ...]
    level: int
    tile: Tile

    @property
    def owner(self) -> int | None:
        """The player who reaches it first, None when none does."""
        return self.reach[0][0] if self.reach else None


@dataclass(frozen=True, slots=True)
class Turn:
    """The rare mines still to stand by family, the guard level each rare family stands
    behind, the days each guard level costs, and the players. A rare slot takes its family
    where it stands: the one that keeps the ways of the players who reach it free of a
    repeat, then one enough are left of for the other players who have not met it, then one
    with no mine of its family close by, then the one the deal gave it. A mine two players
    reach within SLACK days counts on both their ways. A mine within MARGIN tiles past CLOSE
    counts as close, as the mine may stand off the tile it was weighed at. ``guards`` holds
    the level of the guard each standing rare mine stands behind, by the mine's level and
    tile."""

    pool: Counter[str]
    levels: Mapping[str, int]
    toll: Sequence[int]
    players: int
    guards: dict[Key, int] = field(default_factory=dict[Key, int])

    @property
    def offered(self) -> frozenset[str]:
        """The rare families the map offers."""
        return frozenset(self.levels)

    def order(self, at: Stop, standing: Sequence[Stop]) -> list[tuple[str, bool]]:
        """The families a slot dealt ``at.family`` may take at ``at``, best first, once the
        rare mines ``standing`` stand, each with whether it repeats on no way, leaves enough
        for the other players and has no mine of its family close by. ``at.reach`` holds the
        walks there, before the guard."""
        ways = {
            p: [(d, s.family) for s in standing for q, d in s.reach if q == p] for p, _d in at.reach
        }
        met = {(s.owner, s.family) for s in standing}
        mine = {p for p, _d in at.reach}
        others = [q for q in range(self.players) if q not in mine]

        def key(f: str) -> tuple[int, bool, bool, bool, str]:
            toll = self.toll[min(self.levels[f], len(self.toll) - 1)]
            rep = sum(self._late(p, sorted([*ways[p], (d + toll, f)])) for p, d in at.reach)
            lack = sum((q, f) not in met for q in others)
            close = any(
                s.family == f and s.level == at.level and apart(s.tile, at.tile) <= CLOSE + MARGIN
                for s in standing
            )
            return (rep, self.pool[f] <= lack, close, f != at.family, f)

        keyed = sorted((key(f), f) for f, n in self.pool.items() if n > 0)
        return [(f, k[:3] == (0, False, False)) for k, f in keyed]

    def _late(self, player: int, mines: Sequence[tuple[int, str]]) -> int:
        rep = PlayerWay(player, tuple(mines)).repeat(self.offered)
        return 0 if rep is None else len(mines) - rep

    def took(self, family: str) -> None:
        """Count one mine of ``family`` as stood."""
        self.pool[family] -= 1

    def guard_of(self, family: str, obj: PlacedObject) -> int:
        """The level of the guard the rare mine ``obj`` of ``family`` stands behind, its
        family's level when it is not known."""
        return self.guards.get((obj.level, obj.x, obj.y), self.levels[family])


def nearest_first(slots: Sequence[Slot], families: Collection[str]) -> list[Slot]:
    """``slots`` with the slots of ``families`` in the same places, nearest target first."""
    near = iter(
        sorted(
            (s for s in slots if s.family in families),
            key=lambda s: (s.target or 0, s.player or 0),
        )
    )
    return [next(near) if s.family in families else s for s in slots]

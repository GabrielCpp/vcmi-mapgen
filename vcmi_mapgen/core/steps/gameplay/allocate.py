"""Where the promised mines stand: for each basic resource, the spots that bring every player
within PROMISE_DAYS hero-days of a mine of it, with the gap between players kept small.

An offer is a mine anchor in a zone site, priced per player at the tile its guard will stand
on: the travel there plus the toll of the stronger of the guards met on the way and the
mine's own. Each player gets a wood and an ore mine of its own, the nearest that keeps the
gap within PROMISE_GAP. A rare mine may serve several players: a player waits while it is
past PROMISE_DAYS or more than PROMISE_GAP days behind the nearest player. The offer serving
the most waiting players wins, then the one keeping the gap, then the one nearest
RARE_TARGET days. When no offer reaches a late player in time, the nearest one past the
limit takes the mine and a warning says so. A player only behind on the gap gets no mine
that leaves it behind."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Identity, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement.footprint import footprint_cells
from vcmi_mapgen.core.placement.site import ZoneSite
from vcmi_mapgen.core.reading.effort import EffortMap
from vcmi_mapgen.core.reading.promise import PROMISE_DAYS, PROMISE_GAP
from vcmi_mapgen.core.reading.routes import Spot
from vcmi_mapgen.core.steps.gameplay.economy import BASIC_MINE_RES, mine_variants

OWN_GUARD: Mapping[str, int] = {"sawmill": 1, "orePit": 1}
RARE_GUARD = 3
RARE_TARGET = 11
_FAR = 1000

Days = tuple[int | None, ...]
Variants = Callable[[ZoneSite, str], Sequence[Identity]]
Key = tuple[Spot, int, frozenset[Spot]]


def promised_guard(res: str) -> int:
    """The guard level in front of a promised mine of ``res``."""
    return OWN_GUARD.get(res, RARE_GUARD)


@dataclass(frozen=True, slots=True)
class Offer:
    """One anchor for one mine variant in one zone site, with each player's days to it."""

    site: ZoneSite
    ident: Identity
    anchor: Tile
    days: Days


@dataclass(slots=True)
class Pricer:
    """Each player's days to a tile once a guard of a given level stands on it and an object
    blocks the tiles beside it."""

    maps: Sequence[EffortMap]
    seen: dict[Key, Days] = field(default_factory=dict[Key, Days])

    def days(self, spot: Spot, level: int, shut: frozenset[Spot]) -> Days:
        key = (spot, level, shut)
        if key not in self.seen:
            self.seen[key] = tuple(
                None if (e := em.beside(spot, level, shut)) is None else e.total for em in self.maps
            )
        return self.seen[key]


Survey = Callable[[], tuple[Pricer, Mapping[str, Days]]]


def site_variants(catalog: Catalog) -> Variants:
    """The mine variants of a resource whose terrain apron suits a site's terrain."""

    def variants(site: ZoneSite, res: str) -> Sequence[Identity]:
        ids = catalog.mines_by_resource(site.zone.terrain).get(res, [])
        return mine_variants(ids, site.st.anim_w.get(Purpose.MINE, {})) if ids else []

    return variants


def offers(
    sites: Sequence[ZoneSite], variants: Variants, pricer: Pricer, res: str
) -> Iterator[Offer]:
    """Every anchor where a mine of ``res`` may stand, before its fit is checked."""
    level = promised_guard(res)
    for site in sites:
        for ident in variants(site, res):
            for anchor in sorted(site.ts):
                _cells, blocked, approach = footprint_cells(ident.footprint, *anchor)
                if approach is None or approach not in site.reach:
                    continue
                guard = ZoneSite.guard_tile(ident, approach)
                shut = frozenset(Spot(site.lf.level, x, y) for x, y in blocked)
                days = pricer.days(Spot(site.lf.level, *guard), level, shut)
                yield Offer(site, ident, anchor, days)


def _merge(a: int | None, b: int | None) -> int | None:
    if a is None:
        return b
    return a if b is None else min(a, b)


def _late(d: int | None) -> bool:
    return d is None or d > PROMISE_DAYS


def _miss(d: int | None, target: int) -> int:
    if d is None:
        return 2 * _FAR
    return abs(d - target) if d <= PROMISE_DAYS else _FAR + d


def _waiting(best: Days) -> list[int]:
    return [p for p, b in enumerate(best) if _late(b)]


def _behind(best: Days) -> list[int]:
    reached = [b for b in best if b is not None and not _late(b)]
    floor = min(reached, default=PROMISE_DAYS)
    return [p for p, b in enumerate(best) if b is None or _late(b) or b - floor > PROMISE_GAP]


def _excess(best: Days) -> int:
    reached = [b for b in best if b is not None and not _late(b)]
    return max(0, max(reached) - min(reached) - PROMISE_GAP) if reached else 0


def _with(best: Days, days: Days, players: Sequence[int]) -> Days:
    return tuple(
        _merge(b, d) if p in players else b for p, (b, d) in enumerate(zip(best, days, strict=True))
    )


def _served(days: Days, best: Days) -> int:
    return len(_behind(best)) - len(_behind(_with(best, days, range(len(best)))))


def rank(offer: Offer, best: Days, res: str, player: int = 0) -> tuple[int, ...]:
    """The sort key of ``offer`` given each player's ``best`` days so far: lower is better. A
    wood or ore offer serves ``player`` alone, a rare one every player it brings in time and
    within the gap."""
    tail = (offer.site.lf.level, offer.site.zid, *offer.anchor)
    if res in OWN_GUARD:
        after = _with(best, offer.days, [player])
        return (_excess(after), _miss(offer.days[player], 0), *tail)
    after = _with(best, offer.days, range(len(best)))
    miss = sum(_miss(offer.days[p], RARE_TARGET) for p in _behind(best))
    return (-_served(offer.days, best), _excess(after), miss, *tail)


def _stand(offer: Offer, res: str) -> bool:
    site = offer.site
    fit = site.fit(offer.ident, offer.anchor, mine=True)
    if fit is None:
        return False
    obj = site.try_commit(Purpose.MINE, offer.ident, offer.anchor, fit, promised_guard(res))
    return obj is not None


@dataclass(frozen=True, slots=True)
class Kept:
    """The promised mines stood, and a warning per resource left short."""

    stood: tuple[Offer, ...] = ()
    warnings: tuple[str, ...] = ()

    def count(self, site: ZoneSite) -> int:
        """How many promised mines stand in ``site``."""
        return sum(1 for o in self.stood if o.site is site)


def _own(pool: list[Offer], best: Days, res: str, kept: _Ledger) -> None:
    for player in _behind(best):
        pool.sort(key=lambda o: rank(o, best, res, player))
        taken = next((o for o in pool if _stand(o, res)), None)
        if taken is None:
            kept.warnings.append(f"{res}: no spot for player {player}")
            return
        pool.remove(taken)
        kept.stood.append(taken)
        if _late(taken.days[player]):
            kept.warnings.append(f"{res}: player {player} past {PROMISE_DAYS} days")
        best = _with(best, taken.days, [player])


def _shared(pool: list[Offer], best: Days, res: str, kept: _Ledger) -> None:
    while behind := _behind(best):
        pool.sort(key=lambda o: rank(o, best, res))
        useful = pool if _waiting(best) else [o for o in pool if _served(o.days, best) > 0]
        taken = next((o for o in useful if _stand(o, res)), None)
        if taken is None:
            kept.warnings.append(f"{res}: no spot for players {behind}")
            return
        pool.remove(taken)
        kept.stood.append(taken)
        if _served(taken.days, best) <= 0:
            kept.warnings.append(f"{res}: players {behind} past {PROMISE_DAYS} days")
            return
        best = _with(best, taken.days, range(len(best)))


@dataclass(slots=True)
class _Ledger:
    stood: list[Offer] = field(default_factory=list[Offer])
    warnings: list[str] = field(default_factory=list[str])


def keep_promise(sites: Sequence[ZoneSite], variants: Variants, survey: Survey) -> Kept:
    """Stand promised mines until every player reaches each basic resource in time. Each
    player behind on wood or ore gets a mine of its own. A rare mine serves every player it
    reaches in time. ``survey`` reads the map again after each resource that stood a mine,
    so the next resource is priced around it."""
    kept = _Ledger()
    pricer, have = survey()
    for res in BASIC_MINE_RES:
        stood = len(kept.stood)
        best = have.get(res, (None,) * len(pricer.maps))
        pool = list(offers(sites, variants, pricer, res))
        (_own if res in OWN_GUARD else _shared)(pool, best, res, kept)
        if len(kept.stood) > stood:
            pricer, have = survey()
    return Kept(tuple(kept.stood), tuple(kept.warnings))

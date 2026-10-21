"""Where the promised mines stand: for each basic resource, the spots that bring every player
within PROMISE_DAYS hero-days of a mine of it.

An offer is a mine anchor in a zone site, priced per player at the tile its guard will stand
on: the travel there plus the toll of the stronger of the guards met on the way and the
mine's own. Each player gets a wood and an ore mine of its own, the nearest that keeps the
gap within PROMISE_GAP. The rare mines stand as the fewest that bring every player within
PROMISE_DAYS of each rare resource. The rare resources pick in turn, so no spot holds two,
each picking the offer that reaches the most players still out, then the least gap between
them, then the days nearest RARE_TARGET. A pick that later picks of its resource make
redundant is dropped before any mine stands, and a pick that fails to stand gives way to the
next best offer of its resource. A resource no offer brings a player in time to steps its guard
down, and at no guard a warning names the players left out."""

from __future__ import annotations

import random
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Identity, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement.footprint import cell_offsets
from vcmi_mapgen.core.placement.guard_draw import GuardDraw
from vcmi_mapgen.core.placement.site import ZoneSite
from vcmi_mapgen.core.reading.effort import EffortMap
from vcmi_mapgen.core.reading.families import mine_family
from vcmi_mapgen.core.reading.mines import RARE_MINE_RES
from vcmi_mapgen.core.reading.promise import PROMISE_DAYS, PROMISE_GAP
from vcmi_mapgen.core.reading.routes import Spot
from vcmi_mapgen.core.steps.gameplay.economy import mine_variants

OWN_GUARD: Mapping[str, int] = {"sawmill": 1, "orePit": 1}
RARE_GUARD = 3
RARE_TARGET = 11
_FAR = 1000

Days = tuple[int | None, ...]
Variants = Callable[[ZoneSite, str], Sequence[Identity]]
Key = tuple[Spot, int, frozenset[Spot]]
Guarding = Callable[[str], int]


def promised_guard(res: str) -> int:
    """The guard level in front of a promised mine of ``res``."""
    return OWN_GUARD.get(res, RARE_GUARD)


def drawn_guard(draws: GuardDraw, rng: random.Random) -> Guarding:
    """A promised mine's guard drawn from its family's record, never past its promised
    level, so a mine priced at that level is reached no later."""
    return lambda res: min(draws.draw(rng, mine_family(res)), promised_guard(res))


@dataclass(frozen=True, slots=True)
class Offer:
    """One anchor for one mine variant in one zone site, with each player's days to it."""

    site: ZoneSite
    ident: Identity
    anchor: Tile
    days: Days
    cells: frozenset[Spot] = frozenset()


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

    def prime(self, level: int, wants: Iterable[tuple[Spot, frozenset[Spot]]]) -> None:
        todo = [w for w in dict.fromkeys(wants) if (w[0], level, w[1]) not in self.seen]
        spots = [spot for spot, _shut in todo]
        shuts = [shut for _spot, shut in todo]
        rows = [em.besides(spots, level, shuts) for em in self.maps]
        for i, (spot, shut) in enumerate(todo):
            self.seen[spot, level, shut] = tuple(
                None if (e := row[i]) is None else e.total for row in rows
            )


Survey = Callable[[], tuple[Pricer, Mapping[str, Days]]]


def site_variants(catalog: Catalog) -> Variants:
    """The mine variants of a resource whose terrain apron suits a site's terrain."""

    def variants(site: ZoneSite, res: str) -> Sequence[Identity]:
        ids = catalog.mines_by_resource(site.zone.terrain).get(res, [])
        return mine_variants(ids, site.st.anim_w.get(Purpose.MINE, {})) if ids else []

    return variants


def offers(
    sites: Sequence[ZoneSite], variants: Variants, pricer: Pricer, res: str, level: int
) -> Iterator[Offer]:
    """Every anchor where a mine of ``res`` may stand behind a guard of ``level``, before its
    fit is checked."""
    found: list[tuple[ZoneSite, Identity, Tile, Spot, frozenset[Spot], frozenset[Spot]]] = []
    for site in sites:
        lv = site.lf.level
        anchors = sorted(site.ts)
        for ident in variants(site, res):
            body, blocked, offset = cell_offsets(ident.footprint)
            if offset is None:
                continue
            for ax, ay in anchors:
                approach = (ax + offset[0], ay + offset[1])
                if approach not in site.reach:
                    continue
                guard = ZoneSite.guard_tile(ident, approach)
                shut = frozenset(Spot(lv, ax + dx, ay + dy) for dx, dy in blocked)
                cells = frozenset(
                    [
                        *(Spot(lv, ax + dx, ay + dy) for dx, dy in body),
                        Spot(lv, *guard),
                        Spot(lv, *approach),
                    ]
                )
                found.append((site, ident, (ax, ay), Spot(lv, *guard), shut, cells))
    pricer.prime(level, ((spot, shut) for _site, _ident, _anchor, spot, shut, _cells in found))
    for site, ident, anchor, spot, shut, cells in found:
        yield Offer(site, ident, anchor, pricer.days(spot, level, shut), cells)


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


def _out(best: Days) -> list[int]:
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


def keeps_even(best: Days, days: Days) -> bool:
    """Whether a mine each player reaches in ``days`` leaves behind no player that ``best``
    does not, and widens the gap between the players reaching one in time no further."""
    new = _with(best, days, range(len(best)))
    return set(_behind(new)) <= set(_behind(best)) and _excess(new) <= _excess(best)


def rank(offer: Offer, best: Days, player: int = 0) -> tuple[int, ...]:
    """The sort key of ``offer`` given each player's ``best`` days so far: lower is better. A
    wood or ore offer serves ``player`` alone."""
    return (*_merit(offer.days, best, player), *_tail(offer))


def _merit(days: Days, best: Days, player: int) -> tuple[int, ...]:
    after = _with(best, days, [player])
    return (_excess(after), _miss(days[player], 0))


def _tail(offer: Offer) -> tuple[int, ...]:
    return (offer.site.lf.level, offer.site.zid, *offer.anchor)


def _order(pool: list[Offer], best: Days, player: int = 0) -> None:
    merits: dict[Days, tuple[int, ...]] = {}

    def key(offer: Offer) -> tuple[int, ...]:
        merit = merits.get(offer.days)
        if merit is None:
            merit = merits[offer.days] = _merit(offer.days, best, player)
        return (*merit, *_tail(offer))

    pool.sort(key=key)


def _stand(offer: Offer, level: int) -> bool:
    site = offer.site
    fit = site.fit(offer.ident, offer.anchor, mine=True)
    if fit is None:
        return False
    obj = site.try_commit(Purpose.MINE, offer.ident, offer.anchor, fit, level)
    return obj is not None


@dataclass(frozen=True, slots=True)
class Kept:
    """The promised mines stood, and a warning per resource left short."""

    stood: tuple[Offer, ...] = ()
    warnings: tuple[str, ...] = ()
    cover: tuple[tuple[str, int], ...] = ()

    def count(self, site: ZoneSite) -> int:
        """How many promised mines stand in ``site``."""
        return sum(1 for o in self.stood if o.site is site)


def _own(pool: list[Offer], best: Days, res: str, kept: _Ledger, level: int) -> Days:
    for player in _behind(best):
        _order(pool, best, player)
        taken = next((o for o in pool if _stand(o, level)), None)
        if taken is None:
            kept.warnings.append(f"{res}: no spot for player {player}")
            return best
        pool.remove(taken)
        kept.stood.append(taken)
        if _late(taken.days[player]):
            kept.warnings.append(f"{res}: player {player} past {PROMISE_DAYS} days")
        best = _with(best, taken.days, [player])
    return best


@dataclass(slots=True)
class _Ledger:
    stood: list[Offer] = field(default_factory=list[Offer])
    warnings: list[str] = field(default_factory=list[str])


@dataclass(slots=True)
class _Cover:
    res: str
    level: int
    best: Days
    done: bool = False

    @property
    def out(self) -> list[int]:
        return _out(self.best)


def _reached(days: Days, planned: Days) -> list[int]:
    return [d for p in _out(planned) if (d := days[p]) is not None and d <= PROMISE_DAYS]


def _ranked(pool: Sequence[Offer], planned: Days) -> list[Offer]:
    merits: dict[Days, tuple[int, int, int] | None] = {}

    def merit(days: Days) -> tuple[int, int, int] | None:
        if days not in merits:
            got = _reached(days, planned)
            merits[days] = (
                (-len(got), max(got) - min(got), sum(abs(d - RARE_TARGET) for d in got))
                if got
                else None
            )
        return merits[days]

    keyed = [(m, _tail(o), o) for o in pool if (m := merit(o.days)) is not None]
    keyed.sort(key=lambda k: (*k[0], *k[1]))
    return [o for _m, _t, o in keyed]


def _pick(pool: Sequence[Offer], planned: Days, taken: set[Spot]) -> Offer | None:
    return next(
        (
            o
            for o in _ranked(pool, planned)
            if taken.isdisjoint(o.cells) and o.site.fit(o.ident, o.anchor, mine=True) is not None
        ),
        None,
    )


def _round(
    covers: Sequence[_Cover], pools: Mapping[str, Sequence[Offer]]
) -> list[tuple[_Cover, Offer]]:
    taken: set[Spot] = set()
    planned = {c.res: c.best for c in covers}
    active = list(covers)
    chosen: list[tuple[_Cover, Offer]] = []
    while active:
        for c in list(active):
            offer = _pick(pools[c.res], planned[c.res], taken) if _out(planned[c.res]) else None
            if offer is None:
                active.remove(c)
                continue
            chosen.append((c, offer))
            taken |= offer.cells
            planned[c.res] = _with(planned[c.res], offer.days, range(len(offer.days)))
            if not _out(planned[c.res]):
                active.remove(c)
    return chosen


def prune(picks: Sequence[Offer], best: Days) -> list[Offer]:
    """The ``picks`` of one resource in order, less each one, newest first, whose players out
    under ``best`` the other kept picks all reach within PROMISE_DAYS."""
    kept = list(picks)
    for offer in reversed(picks):
        rest = [o for o in kept if o is not offer]
        if all(
            any((d := o.days[p]) is not None and d <= PROMISE_DAYS for o in rest)
            for p in _out(best)
            if (e := offer.days[p]) is not None and e <= PROMISE_DAYS
        ):
            kept = rest
    return kept


@dataclass(slots=True)
class _Rare:
    sites: Sequence[ZoneSite]
    variants: Variants
    survey: Survey
    pricer: Pricer
    kept: _Ledger
    covers: list[_Cover]
    counts: dict[str, int] = field(default_factory=dict[str, int])

    def run(self) -> None:
        while open_ := [c for c in self.covers if not c.done]:
            pools = {
                c.res: list(offers(self.sites, self.variants, self.pricer, c.res, c.level))
                for c in open_
            }
            before = {c.res: len(c.out) for c in open_}
            starts = {c.res: c.best for c in open_}
            chosen = _round(open_, pools)
            keep = {
                id(o) for c in open_ for o in prune([o for k, o in chosen if k is c], starts[c.res])
            }
            if self._stand(chosen, keep, pools):
                self.pricer, have = self.survey()
                for c in self.covers:
                    c.best = have.get(c.res, c.best)
            self._settle(open_, before)

    def _stand(
        self,
        chosen: Sequence[tuple[_Cover, Offer]],
        keep: set[int],
        pools: Mapping[str, Sequence[Offer]],
    ) -> bool:
        cells: set[Spot] = set()
        for c, offer in chosen:
            if id(offer) not in keep or not _reached(offer.days, c.best):
                continue
            got = offer if _stand(offer, c.level) else self._next(pools[c.res], c, cells)
            if got is None:
                continue
            cells |= got.cells
            self.kept.stood.append(got)
            self.counts[c.res] = self.counts.get(c.res, 0) + 1
            c.best = _with(c.best, got.days, range(len(got.days)))
        return bool(cells)

    @staticmethod
    def _next(pool: Sequence[Offer], c: _Cover, cells: set[Spot]) -> Offer | None:
        return next(
            (o for o in _ranked(pool, c.best) if cells.isdisjoint(o.cells) and _stand(o, c.level)),
            None,
        )

    def _settle(self, open_: Sequence[_Cover], before: Mapping[str, int]) -> None:
        for c in open_:
            if len(c.out) >= before[c.res]:
                if c.level == 0:
                    c.done = True
                    self.kept.warnings.append(f"{c.res}: players {c.out} past {PROMISE_DAYS} days")
                else:
                    c.level -= 1
            if not c.out:
                c.done = True


def keep_promise(
    sites: Sequence[ZoneSite],
    variants: Variants,
    survey: Survey,
    guarding: Guarding = promised_guard,
) -> Kept:
    """Stand promised mines until every player reaches each basic resource in time. Each
    player behind on wood or ore gets a mine of its own. The rare mines stand as the fewest
    that bring every player in time, the rare resources picking in turn, each guard stepping
    down one level while a resource leaves a player out, down to no guard. ``survey`` reads
    the map again after each resource of wood and ore, and each round of the rare cover, that
    stood a mine, so the next is priced around it. A second call stands a mine only for a
    player no rare mine reaches in time any more."""
    kept = _Ledger()
    pricer, have = survey()
    for res in OWN_GUARD:
        stood = len(kept.stood)
        best = have.get(res, (None,) * len(pricer.maps))
        for level in range(guarding(res), -1, -1):
            tried = _Ledger()
            pool = list(offers(sites, variants, pricer, res, level))
            best = _own(pool, best, res, tried, level)
            kept.stood.extend(tried.stood)
            if not _behind(best) or level == 0:
                kept.warnings.extend(tried.warnings)
                break
        if len(kept.stood) > stood:
            pricer, have = survey()
    none: Days = (None,) * len(pricer.maps)
    covers = [_Cover(r, guarding(r), have.get(r, none)) for r in RARE_MINE_RES]
    for c in covers:
        c.done = not c.out
    rare = _Rare(sites, variants, survey, pricer, kept, covers)
    rare.run()
    cover = tuple((r, rare.counts.get(r, 0)) for r in RARE_MINE_RES)
    return Kept(tuple(kept.stood), tuple(kept.warnings), cover)

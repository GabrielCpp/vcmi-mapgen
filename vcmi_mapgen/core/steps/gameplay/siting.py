"""Where each planned object stands: the tiles that keep the players' reach of its family even,
then the tiles its player reaches first, nearest its band and its target in days, tried across
the few zone sites that hold the best of them."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from vcmi_mapgen.core.model import PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement.site import NEIGHBOURHOOD, ZoneSite
from vcmi_mapgen.core.reading.effort import EffortMap
from vcmi_mapgen.core.reading.families import family_purpose
from vcmi_mapgen.core.reading.promise import doors
from vcmi_mapgen.core.reading.routes import Spot
from vcmi_mapgen.core.steps.gameplay.bands import Slot
from vcmi_mapgen.core.steps.gameplay.fallback import smaller
from vcmi_mapgen.core.steps.gameplay.pick import Picker
from vcmi_mapgen.core.steps.gameplay.reach import SLACK, Bands, Reach

TOWN_MIN_AREA = 150
MAX_SITES = 4
CENTRES = 40
REPRICE = 12

type Days = tuple[int | None, ...]
type Key = tuple[int, int, int]
type Tier = tuple[int, int]
type Rank = tuple[int, int, int, int, float]


def owner(days: Days) -> int | None:
    """The player who reaches a tile first, the lowest on a tie, None when none does."""
    found = [(d, p) for p, d in enumerate(days) if d is not None]
    return min(found)[1] if found else None


def visit_days(obj: PlacedObject, maps: Sequence[EffortMap]) -> Days:
    """Per player, the fewest days to visit ``obj`` through any of its doors, None when the
    player never does."""
    return tuple(
        min((e.total for d in doors(obj) if (e := em.visit(d)) is not None), default=None)
        for em in maps
    )


def standing_cell(
    obj: PlacedObject, maps: Sequence[EffortMap], band_of: Callable[[int], int]
) -> tuple[int, int] | None:
    """The player who visits ``obj`` first and the band of that visit, None when no player
    reaches it."""
    days = visit_days(obj, maps)
    p = owner(days)
    if p is None:
        return None
    d = days[p]
    return None if d is None else (p, band_of(d))


def hosts(site: ZoneSite, purpose: str) -> bool:
    """Whether ``site`` may hold an object of ``purpose``: a town needs a large zone with no
    town yet."""
    if purpose == Purpose.TOWN:
        return len(site.ts) >= TOWN_MIN_AREA and site.town_center is None
    return True


@dataclass(slots=True)
class Siting:
    """Stands planned objects over the zone sites, each tile priced in days per player, and
    keeps what each player reaches of each family."""

    sites: Sequence[ZoneSite]
    picker: Picker
    band_of: Callable[[int], int]
    rng: random.Random
    reach: Reach
    days: dict[Key, Days] = field(default_factory=dict[Key, Days])
    held: list[tuple[str, PlacedObject]] = field(default_factory=list[tuple[str, PlacedObject]])
    maps: Sequence[EffortMap] = ()

    def price(self, maps: Sequence[EffortMap]) -> None:
        """Price every site tile for each player from ``maps``, as the effort to visit an
        entrance there, and count again what each player reaches."""
        self.days = {
            (s.lf.level, x, y): tuple(
                None if (e := em.visit(Spot(s.lf.level, x, y))) is None else e.total for em in maps
            )
            for s in self.sites
            for x, y in s.ts
        }
        self.maps = maps
        self.reach.clear()
        for family, obj in self.held:
            self.reach.add(family, self._bands_at(obj))

    def track(self, family: str, obj: PlacedObject) -> None:
        """Count ``obj`` of ``family`` in what each player reaches."""
        self.held.append((family, obj))
        self.reach.add(family, self._bands_at(obj))

    def _bands_at(self, obj: PlacedObject) -> Bands:
        return self._bands(visit_days(obj, self.maps))

    def _bands(self, days: Days) -> Bands:
        return tuple(None if d is None else self.band_of(d) for d in days)

    def stand(self, slot: Slot) -> PlacedObject | None:
        """Stand one object of ``slot`` on the best site that takes it, a smaller object of
        the same family when the drawn one finds no room. A mine tries every site, any other
        object the best few. None when no site takes any."""
        purpose = family_purpose(slot.family)
        limit = len(self.sites) if purpose == Purpose.MINE else MAX_SITES
        tried: Counter[Tier] = Counter()
        for tier, site, centres in self._groups(slot, purpose):
            if tier[0] > 0:
                break
            if tried[tier] >= limit:
                continue
            pick = self.picker.pick(slot.family, site.zone.terrain, site.st)
            if pick is None:
                continue
            tried[tier] += 1
            for ident in (pick.ident, *smaller(site, pick.pool, pick.ident)):
                obj = site.place(purpose, ident, centres)
                if obj is not None:
                    self.picker.use(ident)
                    self.track(slot.family, obj)
                    return obj
        return None

    def _groups(self, slot: Slot, purpose: str) -> list[tuple[Tier, ZoneSite, list[Tile]]]:
        keys: dict[Key, Rank] = {}
        owners: dict[Key, int] = {}
        for i, site in enumerate(self.sites):
            if not hosts(site, purpose):
                continue
            level = site.lf.level
            for x, y in site.ts:
                keys[level, x, y] = self._key(slot, self.days.get((level, x, y), ()))
                owners[level, x, y] = i
        tiers = erode({k: (r[0], r[1]) for k, r in keys.items()}, NEIGHBOURHOOD)
        ranked = sorted((tiers[k], keys[k][2:], owners[k], k) for k in keys)
        groups: dict[tuple[Tier, int], list[Tile]] = {}
        for tier, _rest, i, (_level, x, y) in ranked:
            centres = groups.setdefault((tier, i), [])
            if len(centres) < CENTRES:
                centres.append((x, y))
        return [(tier, self.sites[i], centres) for (tier, i), centres in groups.items()]

    def _key(self, slot: Slot, days: Days) -> Rank:
        r = self.rng.random()
        if slot.player is None or slot.band is None or slot.target is None:
            return (0, 0, 0, 0, r)
        spread = self.reach.cost(slot.family, self._bands(days), SLACK)
        reached = [d for d in days if d is not None]
        mine = days[slot.player] if slot.player < len(days) else None
        if mine is None:
            return (spread, 2, 0, 0, r)
        return (
            spread,
            int(mine > min(reached)),
            abs(self.band_of(mine) - slot.band),
            abs(mine - slot.target),
            r,
        )


def erode(tiers: dict[Key, Tier], r: int) -> dict[Key, Tier]:
    """Each tile's worst tier within ``r`` tiles, so an object that slides from its centre
    stays in the tier it was ranked by."""
    rows = {
        (lv, x, y): max(tiers.get((lv, x + d, y), t) for d in range(-r, r + 1))
        for (lv, x, y), t in tiers.items()
    }
    return {
        (lv, x, y): max(rows.get((lv, x, y + d), t) for d in range(-r, r + 1))
        for (lv, x, y), t in rows.items()
    }


def place_slots(
    siting: Siting,
    slots: Sequence[Slot],
    rank: Callable[[str], int],
    price: Callable[[], Sequence[EffortMap]],
) -> Counter[str]:
    """Stand each slot in order, pricing the map again whenever the rank changes and after
    every REPRICE objects. Returns the count placed per family."""
    placed: Counter[str] = Counter()
    last: int | None = None
    since = 0
    for slot in slots:
        r = rank(family_purpose(slot.family))
        if r != last or since >= REPRICE:
            siting.price(price())
            last, since = r, 0
        if siting.stand(slot) is not None:
            placed[slot.family] += 1
            since += 1
    return placed

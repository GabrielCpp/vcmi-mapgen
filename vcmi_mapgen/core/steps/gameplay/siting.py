"""Where each planned object stands: the tiles that keep the players' reach of its family even,
under the weakest guard that does, then the tiles its player reaches first, nearest its band
and its target in days, tried across the few zone sites that hold the best of them."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import cast

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.model import PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement.site import (
    NEIGHBOURHOOD,
    Footing,
    SidedFooting,
    SnugFooting,
    ZoneFooting,
    ZoneSite,
    footing_of,
)
from vcmi_mapgen.core.reading.effort import EffortMap
from vcmi_mapgen.core.reading.families import UNGUARDED, family_purpose
from vcmi_mapgen.core.reading.promise import doors
from vcmi_mapgen.core.reading.routes import Spot
from vcmi_mapgen.core.steps.gameplay.bands import Slot
from vcmi_mapgen.core.steps.gameplay.fair_guard import (
    ARRIVALS,
    FAIR_GUARD,
    Codes,
    TileGrid,
    fair_guard,
)
from vcmi_mapgen.core.steps.gameplay.fallback import smaller
from vcmi_mapgen.core.steps.gameplay.pick import Pick, Picker
from vcmi_mapgen.core.steps.gameplay.reach import SLACK, Bands, Reach

TOWN_MIN_AREA = 150
MAX_SITES = 4
CENTRES = 40
REPRICE = 12

type Days = tuple[int | None, ...]
type Key = tuple[int, int, int]
type Tier = tuple[int, int, int]
type Group = tuple[Tier, ZoneSite, list[Tile]]
type Shape = Callable[[Footing], Footing]

PASSES: tuple[tuple[bool, Shape], ...] = (
    (False, SnugFooting),
    (False, SidedFooting),
    (True, SnugFooting),
    (True, SidedFooting),
)


def owner(days: Days) -> int | None:
    """The player who reaches a tile first, the lowest on a tie, None when none does."""
    found = [(d, p) for p, d in enumerate(days) if d is not None]
    return min(found)[1] if found else None


def visit_days(obj: PlacedObject, maps: Sequence[EffortMap], least: int = 0) -> Days:
    """Per player, the fewest days to visit ``obj`` through any of its doors beating a guard
    of at least ``least``, None when the player never does."""
    return tuple(
        min((e.total for d in doors(obj) if (e := em.visit(d, least)) is not None), default=None)
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


@dataclass(frozen=True, slots=True)
class Tiles:
    """Every site tile in one table: its key, its site, its place on the level grid and its
    days per guard level and player, UNREACHED where the player never reaches it."""

    keys: Sequence[Key]
    site: NDArray[np.intp]
    days: Codes
    grid: TileGrid

    @staticmethod
    def of(sites: Sequence[ZoneSite], maps: Sequence[EffortMap], top: int) -> Tiles:
        keys = [(s.lf.level, x, y) for s in sites for x, y in sorted(s.ts)]
        site = [i for i, s in enumerate(sites) for _t in s.ts]
        spots = [Spot(*k) for k in keys]
        days = [em.visits(spots, top) for em in maps]
        table = (
            np.stack(days, axis=-1) if days else np.zeros((top + 1, len(keys), 0), dtype=np.int64)
        )
        levels = sorted({k[0] for k in keys})
        size = max((max(x, y) for _lv, x, y in keys), default=0) + 1
        grid = TileGrid(
            (len(levels), size, size),
            (
                np.array([levels.index(k[0]) for k in keys], dtype=np.intp),
                np.array([k[2] for k in keys], dtype=np.intp),
                np.array([k[1] for k in keys], dtype=np.intp),
            ),
        )
        return Tiles(keys, np.array(site, dtype=np.intp), table, grid)


@dataclass(slots=True)
class Siting:
    """Stands planned objects over the zone sites, each tile priced in days per player, and
    keeps what each player reaches of each family, each object at its effort past its own
    guard."""

    sites: Sequence[ZoneSite]
    picker: Picker
    band_of: Callable[[int], int]
    rng: random.Random
    reach: Reach
    toll: Sequence[int] = (0,)
    tiles: Tiles | None = None
    held: list[tuple[str, PlacedObject, int]] = field(
        default_factory=list[tuple[str, PlacedObject, int]]
    )
    maps: Sequence[EffortMap] = ()
    _band: Codes = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    _rows: dict[int, tuple[list[Bands], NDArray[np.intp]]] = field(
        default_factory=dict[int, tuple[list[Bands], NDArray[np.intp]]]
    )

    def price(self, maps: Sequence[EffortMap]) -> None:
        """Price every site tile for each player from ``maps``, as the effort to visit an
        entrance there, and count again what each player reaches."""
        self.tiles = Tiles.of(self.sites, maps, min(FAIR_GUARD, len(self.toll) - 1))
        top = max(cast(list[int], self.tiles.days.ravel().tolist()), default=0) + 1
        self._band = np.array([self.band_of(d) for d in range(top)], dtype=np.int64)
        self._rows = {}
        self.maps = maps
        self.reach.clear()
        for family, obj, guard in self.held:
            self.reach.add(family, self._bands_at(obj, guard))

    def track(self, family: str, obj: PlacedObject, guard: int = 0) -> None:
        """Count ``obj`` of ``family`` in what each player reaches, behind its own guard of
        level ``guard``."""
        self.held.append((family, obj, guard))
        self.reach.add(family, self._bands_at(obj, guard))

    def _bands_at(self, obj: PlacedObject, guard: int) -> Bands:
        days = visit_days(obj, self.maps, guard)
        return tuple(None if d is None else self.band_of(d) for d in days)

    def stand(self, slot: Slot) -> PlacedObject | None:
        """Stand one object of ``slot`` on the best site that takes it. The drawn object first
        looks for a spot where it sits snug for its size, then for a spot with one closed
        side. It then gives way to a smaller object of the same family, which looks for the
        same spots in the same order. A mine tries every site, any other object the best few.
        None when no site takes any, and nothing stands."""
        purpose = family_purpose(slot.family)
        limit = len(self.sites) if purpose == Purpose.MINE else MAX_SITES
        groups = self._groups(slot, purpose)
        picks: dict[ZoneSite, Pick | None] = {}
        for fallback, shape in PASSES:
            tried: Counter[Tier] = Counter()
            for tier, site, centres in groups:
                if tried[tier] >= limit:
                    continue
                if site not in picks:
                    picks[site] = self.picker.pick(slot.family, site.zone.terrain, site.st)
                pick = picks[site]
                if pick is None:
                    continue
                tried[tier] += 1
                obj = self._try(slot.family, site, centres, pick, (fallback, shape, tier[1]))
                if obj is not None:
                    return obj
        return None

    def _try(
        self,
        family: str,
        site: ZoneSite,
        centres: list[Tile],
        pick: Pick,
        how: tuple[bool, Shape, int],
    ) -> PlacedObject | None:
        fallback, shape, guard = how
        purpose = family_purpose(family)
        footing = shape(ZoneFooting(mine=True) if guard else footing_of(purpose))
        idents = smaller(site, pick.pool, pick.ident) if fallback else [pick.ident]
        for ident in idents:
            obj = site.place(purpose, ident, centres, footing, guard or None)
            if obj is not None:
                self.picker.use(ident)
                self.track(family, obj, guard)
                return obj
        return None

    def _groups(self, slot: Slot, purpose: str) -> list[Group]:
        """The tiles that widen no gap under their weakest fair guard, best first, grouped by
        tier and site, at most CENTRES per group. A tier is the spread change, the guard
        level and the arrival rank."""
        tiles = self.tiles
        if tiles is None:
            return []
        n = len(tiles.keys)
        counted = np.array([hosts(s, purpose) for s in self.sites], dtype=np.bool_)[tiles.site]
        r = np.random.default_rng(self.rng.getrandbits(64)).random(n)
        zero = np.zeros(n, dtype=np.int64)
        code, guard, band, target = zero, zero, zero, zero
        if slot.player is not None and slot.band is not None and slot.target is not None:
            days = cast(Codes, tiles.days[0])
            reached = days >= 0
            soonest = cast(Codes, np.where(reached, days, np.iinfo(np.int64).max).min(axis=1))
            mine = days[:, slot.player]
            own = np.where(mine < 0, 2, (mine > soonest).astype(np.int64))
            at = np.maximum(mine, 0)
            band = np.where(mine < 0, 0, np.abs(self._band[at] - slot.band))
            target = np.where(mine < 0, 0, np.abs(at - slot.target))
            family = slot.family
            code, guard = fair_guard(
                lambda level: self._spreads(family, level) * ARRIVALS + own,
                0 if purpose in UNGUARDED else min(FAIR_GUARD, len(self.toll) - 1),
                lambda c: tiles.grid.worst_within(c, NEIGHBOURHOOD, counted),
            )
        spread, own = np.divmod(code, ARRIVALS)
        order = cast(NDArray[np.intp], np.lexsort((r, target, band, own, guard, spread)))
        kept = order[(counted & (code < ARRIVALS))[order]]
        tiers = cast(
            list[list[int]], np.stack((spread, guard, own, tiles.site))[:, kept].T.tolist()
        )
        groups: dict[tuple[Tier, int], list[Tile]] = {}
        for k, (s, g, o, i) in zip(cast(list[int], kept.tolist()), tiers, strict=True):
            centres = groups.setdefault(((s, g, o), i), [])
            if len(centres) < CENTRES:
                _lv, x, y = tiles.keys[k]
                centres.append((x, y))
        return [(tier, self.sites[i], centres) for (tier, i), centres in groups.items()]

    def _spreads(self, family: str, level: int) -> Codes:
        rows, back = self._patterns(level)
        cost = [self.reach.cost(family, row, SLACK) for row in rows]
        return np.array(cost, dtype=np.int64)[back]

    def _patterns(self, level: int) -> tuple[list[Bands], NDArray[np.intp]]:
        if level not in self._rows:
            tiles = self.tiles
            assert tiles is not None
            days = cast(Codes, tiles.days[level])
            bands = np.where(days >= 0, self._band[np.maximum(days, 0)], 0)
            rows, back = np.unique(bands, axis=0, return_inverse=True)
            self._rows[level] = (
                [
                    tuple(None if b == 0 else b for b in row)
                    for row in cast(list[list[int]], rows.tolist())
                ],
                back.reshape(-1),
            )
        return self._rows[level]


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

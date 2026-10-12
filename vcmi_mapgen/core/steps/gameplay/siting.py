"""Where each planned object stands. Each object first draws its own guard from its family's
corpus record, and every tile is ranked once under that guard. An object of no player stands
first on the tiles that keep the players' reach of its family even, nearest its band, furthest
from every object already standing, nearest its target in days. A rare mine stands first on
the even tiles its player reaches first, nearest its band and its target. Either tries an
uneven tile only after every even one, and tries the few zone sites that hold the best of
them. A neutral town stands on the even tiles furthest from every
town already standing. A gold mine stands where the gold rule admits it, the best of its rank
first, and where the loose gold rule admits it when no such tile takes it.

A tile's tier code is its spread change times ARRIVALS plus its arrival rank, so codes order
as the pair does and a code below ARRIVALS widens no gap."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import cast

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.model import PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement.fallback import smaller
from vcmi_mapgen.core.placement.guard_draw import GuardDraw
from vcmi_mapgen.core.placement.site import (
    NEIGHBOURHOOD,
    Footing,
    OpenFooting,
    SidedFooting,
    SnugFooting,
    ZoneSite,
    footing_for,
    large,
    openness,
)
from vcmi_mapgen.core.priors.effort import BANDS
from vcmi_mapgen.core.reading.contest import soonest
from vcmi_mapgen.core.reading.effort import EffortMap
from vcmi_mapgen.core.reading.families import (
    TOP_LEVEL,
    UNGUARDED,
    door_guard,
    family_purpose,
    guard_levels,
    mine_family,
)
from vcmi_mapgen.core.reading.mines import BASIC_MINE_RES, GOLD
from vcmi_mapgen.core.reading.promise import doors
from vcmi_mapgen.core.reading.routes import Spot
from vcmi_mapgen.core.reading.supply import NEAR, entrance
from vcmi_mapgen.core.steps.gameplay.allocate import keeps_even, promised_guard
from vcmi_mapgen.core.steps.gameplay.bands import Slot
from vcmi_mapgen.core.steps.gameplay.gold import GoldSpot
from vcmi_mapgen.core.steps.gameplay.pick import Pick, Picker
from vcmi_mapgen.core.steps.gameplay.reach import SLACK, Bands, Reach
from vcmi_mapgen.core.steps.gameplay.turn import Stop, Turn, near

MAX_SITES = 4
CENTRES = 40
TOWN_ROOM = 238
REPRICE = 12
ARRIVALS = 3
GOLD_FAMILY = mine_family(GOLD)
PROMISED = {mine_family(r): r for r in BASIC_MINE_RES}

type Days = tuple[int | None, ...]
type Codes = NDArray[np.int64]
type Key = tuple[int, int, int]
type Tier = tuple[int, int, int]
type Group = tuple[Tier, ZoneSite, NDArray[np.intp]]
type Shape = Callable[[Footing], Footing]

PASSES: tuple[tuple[bool, Shape], ...] = (
    (False, SnugFooting),
    (False, SidedFooting),
    (False, OpenFooting),
    (True, SnugFooting),
    (True, SidedFooting),
    (True, OpenFooting),
)


@dataclass(frozen=True, slots=True)
class TileGrid:
    """Where each ranked tile sits on a (levels, rows, columns) grid."""

    shape: tuple[int, int, int]
    cells: tuple[NDArray[np.intp], NDArray[np.intp], NDArray[np.intp]]

    def worst_within(self, values: Codes, r: int) -> Codes:
        """Per tile, the largest of ``values`` within ``r`` tiles along its row, then along its
        column."""
        low = np.iinfo(np.int64).min
        present = np.zeros(self.shape, dtype=np.bool_)
        present[self.cells] = True
        grid = np.full(self.shape, low, dtype=np.int64)
        grid[self.cells] = values
        for axis in (2, 1):
            grid = np.where(present, _slide(grid, axis, r, low), low)
        return grid[self.cells]


def _slide(a: Codes, axis: int, r: int, low: int) -> Codes:
    n = a.shape[axis]
    pad = [(0, 0)] * 3
    pad[axis] = (r, r)
    padded = np.pad(a, pad, constant_values=low)
    best = a.copy()
    for d in range(2 * r + 1):
        window = [slice(None)] * 3
        window[axis] = slice(d, d + n)
        _ = np.maximum(best, padded[tuple(window)], out=best)
    return best


def _sooner(a: int | None, b: int | None) -> int | None:
    return b if a is None else a if b is None else min(a, b)


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


def standing_visit(obj: PlacedObject, maps: Sequence[EffortMap]) -> tuple[int, int] | None:
    """The player who visits ``obj`` first and the days of that visit, None when no player
    reaches it."""
    days = visit_days(obj, maps)
    p = owner(days)
    if p is None:
        return None
    d = days[p]
    return None if d is None else (p, d)


@dataclass(frozen=True, slots=True)
class Tiles:
    """Every site tile in one table: its key, its site, its place on the level grid and its
    days per guard level and player, UNREACHED where the player never reaches it."""

    keys: Sequence[Key]
    site: NDArray[np.intp]
    days: Codes
    grid: TileGrid
    spots: Sequence[Spot] = ()

    @staticmethod
    def laid(sites: Sequence[ZoneSite]) -> Tiles:
        """The site tiles, not yet priced."""
        keys = [(s.lf.level, x, y) for s in sites for x, y in sorted(s.ts)]
        site = [i for i, s in enumerate(sites) for _t in s.ts]
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
        days = np.zeros((0, len(keys), 0), dtype=np.int64)
        return Tiles(keys, np.array(site, dtype=np.intp), days, grid, [Spot(*k) for k in keys])

    def priced(self, maps: Sequence[EffortMap], top: int) -> Tiles:
        """These tiles, each priced for each player from ``maps``."""
        days = [em.visits(self.spots, top) for em in maps]
        table = (
            np.stack(days, axis=-1)
            if days
            else np.zeros((top + 1, len(self.keys), 0), dtype=np.int64)
        )
        return Tiles(self.keys, self.site, table, self.grid, self.spots)


@dataclass(slots=True)
class Siting:
    """Stands planned objects over the zone sites, each tile priced in days per player, each
    object behind the guard ``draws`` gives it, and keeps what each player reaches of each
    family, each object at its effort past its own guard."""

    sites: Sequence[ZoneSite]
    picker: Picker
    band_of: Callable[[int], int]
    rng: random.Random
    reach: Reach
    toll: Sequence[int] = (0,)
    draws: GuardDraw = field(default_factory=GuardDraw)
    tiles: Tiles | None = None
    held: list[tuple[str, PlacedObject, int]] = field(
        default_factory=list[tuple[str, PlacedObject, int]]
    )
    maps: Sequence[EffortMap] = ()
    turn: Turn | None = None
    gold: GoldSpot | None = None
    homes: Sequence[PlacedObject] = ()
    _band: Codes = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    _firsts: dict[int, tuple[NDArray[np.bool_], Codes, Codes]] = field(
        default_factory=dict[int, tuple[NDArray[np.bool_], Codes, Codes]]
    )
    _gap: Codes | None = None
    _seen: int = 0
    _rows: dict[int, tuple[list[Bands], NDArray[np.intp]]] = field(
        default_factory=dict[int, tuple[list[Bands], NDArray[np.intp]]]
    )

    def price(self, maps: Sequence[EffortMap]) -> None:
        """Price every site tile for each player from ``maps``, as the effort to visit an
        entrance there, and count again what each player reaches."""
        laid = Tiles.laid(self.sites) if self.tiles is None else self.tiles
        self.tiles = laid.priced(maps, self._top())
        top = max(cast(list[int], self.tiles.days.ravel().tolist()), default=0) + 1
        self._band = np.array([self.band_of(d) for d in range(top)], dtype=np.int64)
        self._rows = {}
        self._firsts = {}
        self.maps = maps
        self.reach.clear()
        for family, obj, guard in self.held:
            self.reach.add(family, self._bands_at(obj, guard))

    def _top(self) -> int:
        return min(TOP_LEVEL, len(self.toll) - 1)

    def track(self, family: str, obj: PlacedObject, guard: int = 0) -> None:
        """Count ``obj`` of ``family`` in what each player reaches, behind its own guard of
        level ``guard``."""
        self.held.append((family, obj, guard))
        self.reach.add(family, self._bands_at(obj, guard))

    def _bands_at(self, obj: PlacedObject, guard: int) -> Bands:
        days = visit_days(obj, self.maps, guard)
        return tuple(None if d is None else self.band_of(d) for d in days)

    def stand(self, slot: Slot) -> tuple[str, PlacedObject] | None:
        """Stand one object of ``slot`` on the best site that takes it, with its family, behind
        the guard drawn for its family. The drawn object first looks for a spot where it sits
        snug for its size, then for a spot with one closed side, then for any spot in the open.
        It then gives way to a smaller object of the same family, which looks for the same
        spots in the same order. A large object, and any object in the open, tries the most
        open ground of a group first. A mine or a town tries every site, any other object the
        best few. A rare mine takes its family from the turn where it stands. None when no
        site takes any, and nothing stands."""
        purpose = family_purpose(slot.family)
        guard = min(self.draws.draw(self.rng, slot.family), self._top())
        if self.gold is not None and slot.family == GOLD_FAMILY:
            return self._stand_gold(slot, purpose, guard)
        groups = self._groups(slot, purpose, guard)
        picks: dict[tuple[ZoneSite, str, int], Pick | None] = {}
        stops = self._stops(slot.family)
        for strict in (True, False) if stops is not None and groups else (False,):
            near = [g for g in groups if g[0] == groups[0][0]] if strict else groups
            stood = self._stand(slot.family, near, (picks, stops), strict)
            if stood is not None:
                return stood
        return None

    def _stand_gold(self, slot: Slot, purpose: str, guard: int) -> tuple[str, PlacedObject] | None:
        picks: dict[tuple[ZoneSite, str, int], Pick | None] = {}
        for loose in (False, True):
            groups = self._groups(slot, purpose, guard, loose)
            stood = self._stand(slot.family, groups, (picks, None), False)
            if stood is not None:
                return stood
        return None

    def _stand(
        self,
        dealt: str,
        groups: Sequence[Group],
        seen: tuple[dict[tuple[ZoneSite, str, int], Pick | None], Sequence[Stop] | None],
        strict: bool,
    ) -> tuple[str, PlacedObject] | None:
        every = family_purpose(dealt) in (Purpose.MINE, Purpose.TOWN)
        limit = len(self.sites) if every else MAX_SITES
        for fallback, shape in PASSES:
            tried: Counter[Tier] = Counter()
            for tier, site, rows in groups:
                if tried[tier] >= limit:
                    continue
                parts = self._parts(dealt, site, rows, seen, strict)
                tried[tier] += bool(parts)
                for family, pick, part in parts:
                    centres = self._centres(part)
                    guard = self._even_guard(family, cast(list[int], part[:1].tolist())[0], tier[1])
                    obj = self._try(family, site, centres, pick, (fallback, shape, guard))
                    if obj is not None:
                        self._took(family, site, obj)
                        return family, obj
        return None

    def _even_guard(self, family: str, k: int, guard: int) -> int:
        """The guard a mine of a promised resource stands behind at tile ``k``: the lowest
        level from ``guard`` up to its promised level that keeps the players even on its
        resource, the promised level when none does. Any other object keeps ``guard``."""
        res = PROMISED.get(family)
        tiles = self.tiles
        if res is None or tiles is None:
            return guard
        top = promised_guard(res)
        best = self._nearest(family)
        for level in range(guard, top):
            row = cast(list[int], cast(Codes, tiles.days[level, k]).tolist())
            if keeps_even(best, tuple(None if d < 0 else d for d in row)):
                return level
        return max(guard, top)

    def _nearest(self, family: str) -> Days:
        """Per player, the fewest days to a standing object of ``family`` past its own guard."""
        turn = self.turn
        best: list[int | None] = [None] * len(self.maps)
        for f, obj, guard in self.held:
            if f == family:
                least = turn.guard_of(f, obj) if turn is not None and f in turn.offered else guard
                for p, d in enumerate(visit_days(obj, self.maps, least)):
                    best[p] = _sooner(best[p], d)
        return tuple(best)

    def _took(self, family: str, site: ZoneSite, obj: PlacedObject) -> None:
        turn = self.turn
        if turn is not None and family in turn.offered:
            turn.took(family)
            guards = guard_levels(self.picker.catalog, site.objs)
            turn.guards[obj.level, obj.x, obj.y] = door_guard(guards, obj)

    def _parts(
        self,
        dealt: str,
        site: ZoneSite,
        rows: NDArray[np.intp],
        seen: tuple[dict[tuple[ZoneSite, str, int], Pick | None], Sequence[Stop] | None],
        strict: bool,
    ) -> list[tuple[str, Pick, NDArray[np.intp]]]:
        picks, stops = seen
        if stops is None:
            drawn = self._first(picks, site, [dealt], cast(list[int], rows[:1].tolist())[0])
            return [] if drawn is None else [(*drawn, rows)]
        parts: dict[str, tuple[Pick, list[int]]] = {}
        for k in cast(list[int], rows.tolist()):
            drawn = self._first(picks, site, self._turns(dealt, site, k, stops, strict), k)
            if drawn is not None:
                parts.setdefault(drawn[0], (drawn[1], []))[1].append(k)
        return [(f, p, np.array(ks, dtype=np.intp)) for f, (p, ks) in parts.items()]

    def _first(
        self,
        picks: dict[tuple[ZoneSite, str, int], Pick | None],
        site: ZoneSite,
        families: list[str],
        k: int,
    ) -> tuple[str, Pick] | None:
        tiles = self.tiles
        assert tiles is not None
        for family in families:
            if (site, family, k) not in picks:
                at = tiles.keys[k]
                picks[site, family, k] = self.picker.pick(family, site.zone.terrain, site.st, at)
            pick = picks[site, family, k]
            if pick is not None:
                return family, pick
        return None

    def _stops(self, family: str) -> list[Stop] | None:
        turn = self.turn
        if turn is None or family not in turn.offered:
            return None
        stops: list[Stop] = []
        for f, obj, _guard in self.held:
            if f in turn.offered:
                reach = near(visit_days(obj, self.maps, turn.guard_of(f, obj)))
                stops.append(Stop(f, reach, obj.level, entrance(obj)))
        return stops

    def _turns(
        self,
        dealt: str,
        site: ZoneSite,
        k: int,
        stops: Sequence[Stop],
        strict: bool,
    ) -> list[str]:
        tiles, turn = self.tiles, self.turn
        assert tiles is not None and turn is not None
        days = cast(list[int], cast(Codes, tiles.days[0, k]).tolist())
        reach = near([None if d < 0 else d for d in days])
        at = Stop(dealt, reach, site.lf.level, tiles.keys[k][1:])
        return [f for f, clean in turn.order(at, stops) if clean or not strict]

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
        footing = shape(footing_for(purpose, guard))
        idents = smaller(site, pick.pool, pick.ident) if fallback else [pick.ident]
        for ident in idents:
            opens = large(ident) or shape is OpenFooting
            at = self._open_first(site, centres) if opens else centres
            spots = self.picker.clear_first(ident, site.lf.level, at)
            obj = site.place(purpose, ident, spots, footing, guard)
            if obj is not None:
                self.picker.use(ident, obj)
                self.track(family, obj, 0 if purpose in UNGUARDED else guard)
                return obj
        return None

    @staticmethod
    def _open_first(site: ZoneSite, centres: list[Tile]) -> list[Tile]:
        room = {c: openness(site, c, NEIGHBOURHOOD) for c in centres}
        return sorted(centres, key=lambda c: -room[c])

    def _groups(self, slot: Slot, purpose: str, guard: int, loose: bool = False) -> list[Group]:
        """The tiles under a guard of level ``guard``, those that widen the gap least first,
        grouped by tier and site, at most CENTRES per group. A tier is the spread change, or the
        bands off for an object of no player, then the guard level and the arrival rank. A gold
        mine keeps only the tiles the gold rule admits, or the ``loose`` gold rule. A neutral
        town keeps only the tiles with TOWN_ROOM tiles of land around them, ranks those that
        widen the gap least first, then furthest from every town. Any other object of no player
        ranks by its band, then furthest from every object standing, then by its target,
        whatever spread it leaves between the players."""
        tiles = self.tiles
        if tiles is None:
            return []
        n = len(tiles.keys)
        r = np.random.default_rng(self.rng.getrandbits(64)).random(n)
        zero = np.zeros(n, dtype=np.int64)
        level = 0 if purpose in UNGUARDED else guard
        held = np.full(n, guard, dtype=np.int64)
        code, band, target = zero, zero, zero
        ok = np.ones(n, dtype=np.bool_)
        days = cast(Codes, tiles.days[0])
        if self.gold is not None and slot.family == GOLD_FAMILY:
            gold = replace(self.gold, guard=self.toll[guard])
            ok, target = gold.rank(days, loose)
            code = self._code(slot.family, level, zero)
        elif purpose == Purpose.TOWN and slot.player is None:
            code = self._code(slot.family, level, zero)
            spread = code // ARRIVALS
            gap = town_gap(tiles, self._towns())
            ok = town_room(tiles, self.sites) >= TOWN_ROOM
            order = cast(NDArray[np.intp], np.lexsort((r, -gap, spread)))
            kept = order[ok[order]]
            return self._grouped(tiles, kept, np.stack((spread, held, zero))[:, kept])
        elif slot.player is None and slot.band is not None and slot.target is not None:
            reached, at, arrival = self._arrival(level)
            off = np.where(reached, np.abs(arrival - slot.band), BANDS)
            target = np.where(reached, np.abs(at - slot.target), 0)
            gap = self._gaps()
            order = cast(NDArray[np.intp], np.lexsort((r, target, -gap, off)))
            return self._grouped(tiles, order, np.stack((off, held, zero))[:, order])
        elif slot.player is not None and slot.band is not None and slot.target is not None:
            mine = days[:, slot.player]
            own = np.where(mine < 0, 2, (mine > soonest(days)).astype(np.int64))
            at = np.maximum(mine, 0)
            band = np.where(mine < 0, 0, np.abs(self._band[at] - slot.band))
            target = np.where(mine < 0, 0, np.abs(at - slot.target))
            code = self._code(slot.family, level, own)
        spread, own = np.divmod(code, ARRIVALS)
        order = cast(NDArray[np.intp], np.lexsort((r, target, band, own, spread)))
        kept = order[ok[order]]
        return self._grouped(tiles, kept, np.stack((spread, held, own))[:, kept])

    def _code(self, family: str, level: int, own: Codes) -> Codes:
        """Per tile, the worst tier code within NEIGHBOURHOOD of it, the object behind a guard
        of ``level`` and ``own`` its arrival rank."""
        tiles = self.tiles
        assert tiles is not None
        return tiles.grid.worst_within(self._spreads(family, level) * ARRIVALS + own, NEIGHBOURHOOD)

    def _arrival(self, level: int) -> tuple[NDArray[np.bool_], Codes, Codes]:
        """Per tile under a guard of ``level``, whether a player visits it, the first visit
        in days and its band."""
        if level not in self._firsts:
            tiles = self.tiles
            assert tiles is not None
            first = soonest(cast(Codes, tiles.days[level]))
            at = np.minimum(first, len(self._band) - 1)
            self._firsts[level] = (first < len(self._band), at, self._band[at])
        return self._firsts[level]

    def _gaps(self) -> Codes:
        """Per tile, the tiles to the nearest gameplay object or home on its level, as
        `town_gap` reads them."""
        tiles = self.tiles
        assert tiles is not None
        if self._gap is None:
            self._gap, self._seen = town_gap(tiles, self.homes), 0
        new = [o for _f, o, _g in self.held[self._seen :]]
        if new:
            self._gap = np.minimum(self._gap, town_gap(tiles, new))
        self._seen = len(self.held)
        return self._gap

    def _grouped(self, tiles: Tiles, kept: NDArray[np.intp], tier: Codes) -> list[Group]:
        if len(kept) == 0:
            return []
        step = np.concatenate(([0], np.any(np.not_equal(tier[:, 1:], tier[:, :-1]), axis=0)))
        key = np.cumsum(step) * len(self.sites) + tiles.site[kept]
        _keys, first, member = np.unique(key, return_index=True, return_inverse=True)
        by = kept[np.argsort(member, kind="stable")]
        counts = np.bincount(member)
        starts = cast(list[int], (np.cumsum(counts) - counts).tolist())
        sizes = cast(list[int], np.minimum(counts, CENTRES).tolist())
        heads = cast(list[int], tiles.site[kept[first]].tolist())
        tiers = cast(list[list[int]], tier[:, first].T.tolist())
        groups: list[Group] = []
        for g in cast(list[int], np.argsort(first).tolist()):
            s, gd, o = tiers[g]
            groups.append(((s, gd, o), self.sites[heads[g]], by[starts[g] : starts[g] + sizes[g]]))
        return groups

    def _towns(self) -> list[PlacedObject]:
        homes = {id(o) for o in self.homes}
        stood = [o for s in self.sites for o in s.objs if o.purpose == Purpose.TOWN]
        return [*self.homes, *(o for o in stood if id(o) not in homes)]

    def _centres(self, rows: NDArray[np.intp]) -> list[Tile]:
        tiles = self.tiles
        assert tiles is not None
        return [(tiles.keys[k][1], tiles.keys[k][2]) for k in cast(list[int], rows.tolist())]

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
            rows, back = _unique_rows(bands)
            self._rows[level] = (
                [
                    tuple(None if b == 0 else b for b in row)
                    for row in cast(list[list[int]], rows.tolist())
                ],
                back.reshape(-1),
            )
        return self._rows[level]


def town_gap(tiles: Tiles, towns: Sequence[PlacedObject]) -> Codes:
    """Per tile, the tiles to the centre of the nearest of ``towns`` on its level, or to its
    mirror image across the nearest map edge when that is nearer, rounded down."""
    _lv, rows, cols = tiles.grid.shape
    keys: NDArray[np.float64] = np.array(tiles.keys, dtype=np.float64).reshape(-1, 3)
    level, x, y = keys[:, 0], keys[:, 1], keys[:, 2]
    edge = np.minimum(np.minimum(x + 1, cols - x), np.minimum(y + 1, rows - y))
    gap = (2 * edge).astype(np.int64)
    for town in towns:
        cx = town.x - (town.footprint.width - 1) / 2.0
        cy = town.y - (town.footprint.height - 1) / 2.0
        d = np.where(np.equal(level, town.level), np.hypot(x - cx, y - cy), np.inf)
        gap = np.minimum(gap, np.minimum(d, rows + cols).astype(np.int64))
    return gap


def town_room(tiles: Tiles, sites: Sequence[ZoneSite]) -> Codes:
    """Per tile, the tiles of land, neither water nor rock, within NEAR of it on its level."""
    room = np.zeros(len(tiles.keys), dtype=np.int64)
    keys: NDArray[np.intp] = np.array(tiles.keys, dtype=np.intp).reshape(-1, 3)
    fields = {s.lf.level: s.lf for s in sites}
    for level, lf in fields.items():
        w, h = lf.size
        land = np.ones((h + 2 * NEAR, w + 2 * NEAR), dtype=np.int64)
        land[:NEAR, :] = 0
        land[-NEAR:, :] = 0
        land[:, :NEAR] = 0
        land[:, -NEAR:] = 0
        for x, y in lf.barrier:
            land[y + NEAR, x + NEAR] = 0
        sums = np.zeros((h + 2 * NEAR + 1, w + 2 * NEAR + 1), dtype=np.int64)
        sums[1:, 1:] = land.cumsum(axis=0).cumsum(axis=1)
        on = np.equal(keys[:, 0], level)
        x = cast(NDArray[np.intp], keys[on, 1])
        y = cast(NDArray[np.intp], keys[on, 2])
        side = 2 * NEAR + 1
        room[on] = sums[y + side, x + side] - sums[y, x + side] - sums[y + side, x] + sums[y, x]
    return room


def _unique_rows(rows: Codes) -> tuple[Codes, NDArray[np.intp]]:
    """``np.unique(rows, axis=0, return_inverse=True)`` for rows of small non-negative codes,
    each row read as one number so the sort runs over a single column."""
    base = int(cast(int, rows.max(initial=0))) + 1
    if base ** rows.shape[1] >= 2**62:
        return np.unique(rows, axis=0, return_inverse=True)
    key: Codes = np.zeros(rows.shape[0], dtype=np.int64)
    for j in range(rows.shape[1]):
        key = np.add(np.multiply(key, base), rows[:, j])
    _keys, first, back = np.unique(key, return_index=True, return_inverse=True)
    return rows[first], back


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
        stood = siting.stand(slot)
        if stood is not None:
            placed[stood[0]] += 1
            since += 1
    return placed

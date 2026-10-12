"""Gameplay spots against the vegetated field: one ``LevelField`` per level holds what every
zone shares (unwalkable tiles, gameplay footprints, the cover index, the terrain rule), one
``ZoneSite`` per zone finds and commits a spot for each object.

A ``Footing`` picked by purpose decides which anchors a zone site tries and whether a body may stand
on one. ``ZoneFooting`` keeps the footprint in the zone clear of other gameplay blocking cells, so
two bodies may stand side by side, and off the entrance bands and earlier approaches.
``TownFooting`` only keeps a town off other footprints and earlier approaches, and lets its cells
spill out of the zone onto unwalkable land that is not water or rock. Under either footing the
entrance and its approach are walkable and reachable from the web, and the blocking cells split no
reachable area in two nor part the open tiles beside them that joined through them. Blocking cells
may land on vegetation, the zone rim and the web, and the web then walks around them.
``SnugFooting`` narrows a footing to the anchors where the object sits snug for its size, and
``SidedFooting`` to the anchors with a closed tile on or around the sprite. Among the legal
anchors of a neighbourhood the one whose sprite top and flanks rest most against unwalkable tiles
wins. While a level hems fewer objects than HEMMED_SHARE, a commit plants a decoration on each
open flank it can close without cutting a path."""

from __future__ import annotations

import collections
import math
import random
from collections.abc import Iterable, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from typing import Protocol, cast, final

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.components import components
from vcmi_mapgen.core.grid.detour import detours
from vcmi_mapgen.core.grid.flanks import closed_flanks, flank_tiles
from vcmi_mapgen.core.grid.reach import walk
from vcmi_mapgen.core.grid.snug import SIZE_CLASSES, in_field, sided, size_class, snug
from vcmi_mapgen.core.grid.splits import MIN_AREA, splits
from vcmi_mapgen.core.model import (
    CoverIndex,
    Footprint,
    Guard,
    Identity,
    Payload,
    PlacedObject,
    PlacementRule,
    Role,
    Tile,
    Town,
)
from vcmi_mapgen.core.model.purpose import FLANKED, Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.placement.footprint import footprint_cells, overlay_cells
from vcmi_mapgen.core.placement.ground import Ground, stands
from vcmi_mapgen.core.placement.guards import (
    GAP,
    NO_TILES,
    Clearance,
    Fit,
    fits,
    guard_zoc,
    inflate_gap,
    zoc_of,
)
from vcmi_mapgen.core.placement.place import web_dist
from vcmi_mapgen.core.priors.gameplay import HEMMED_SHARE, TerrainStats

# guard strength tracks the value guarded: mine guards by resource rarity. Every mine is
# guarded (user-reported bug: unguarded mines), valuable mines scaling higher still. The
# town's own economy pair (sawmill/orePit) is guarded at level 1 specifically (user-mandated
# — a trivial early fight, not a level-3+ wall in front of every town's starting economy).
MINE_GUARD_LVL = {
    "sawmill": 1,
    "orePit": 1,
    "alchemistLab": 4,
    "sulfurDune": 4,
    "gemPond": 5,
    "crystalCavern": 5,
    "goldMine": 6,
    "abandoned": 5,
}

SITE_SALT = 0xA77A
NEIGHBOURHOOD = 3
_WINDOW = tuple(
    (dx, dy)
    for dx in range(-NEIGHBOURHOOD, NEIGHBOURHOOD + 1)
    for dy in range(-NEIGHBOURHOOD, NEIGHBOURHOOD + 1)
)
FLANK_WEIGHT = 2
MIN_WEIGHT = 1e-300


def back_score(
    fp: Footprint, anchor: Tile, unwalkable: AbstractSet[Tile], size: tuple[int, int]
) -> int:
    """Per sprite column, the topmost drawn tile scores 1 when it is unwalkable and 1 more
    when the tile above it is. Off-map counts as unwalkable. A 1-tile object scores 0."""
    cells = [t for t, _role in fp.at(*anchor)]
    if len(cells) < 2:
        return 0
    top: dict[int, int] = {}
    for x, y in cells:
        top[x] = min(y, top.get(x, y))
    w, h = size

    def bad(x: int, y: int) -> int:
        return int(not (0 <= x < w and 0 <= y < h) or (x, y) in unwalkable)

    return sum(bad(x, y) + bad(x, y - 1) for x, y in top.items())


def door_cells(fp: Footprint, anchor: Tile) -> list[Tile]:
    return [t for t, role in fp.at(*anchor) if role.interactive]


def walk_on_only(fp: Footprint) -> bool:
    return all(role is not Role.ENTRANCE for _dx, _dy, role in fp.cells)


def path_to_web(start: Tile, web: AbstractSet[Tile], passable: AbstractSet[Tile]) -> list[Tile]:
    """The shortest 4-connected walk from ``start`` to the nearest web tile, both ends
    included, or an empty list when none exists."""
    return walk([start], web, passable)


def _walk(src: AbstractSet[Tile], dst: AbstractSet[Tile], passable: AbstractSet[Tile]) -> set[Tile]:
    return set(walk(sorted(src), dst, passable))


def mend(web: AbstractSet[Tile], cut: AbstractSet[Tile], passable: AbstractSet[Tile]) -> set[Tile]:
    """The web without ``cut``, each piece the cut split off rejoined by a shortest walk
    through ``passable``."""
    before = components(web)
    left = set(web) - set(cut)
    after = components(left)
    pieces: dict[int, dict[int, set[Tile]]] = collections.defaultdict(dict)
    for t in left:
        pieces[before[t]].setdefault(after[t], set()).add(t)
    for parts in pieces.values():
        order = sorted(parts)
        joined = set(parts[order[0]])
        for i in order[1:]:
            path = _walk(joined, parts[i], passable)
            joined |= parts[i] | path
            left |= path
    return left


def es_key(rng: random.Random, weight: float) -> float:
    return math.log(1.0 - rng.random()) / max(weight, MIN_WEIGHT)


def payload_for(purpose: str) -> Payload | None:
    if purpose == Purpose.GUARD:
        return Guard()
    if purpose == Purpose.TOWN:
        return Town()
    return None


def cheb(a: Tile, b: Tile) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


@dataclass(slots=True)
class LevelField:
    """What every zone of one level shares. ``unwalkable`` is water, rock and every blocking
    cell on the level, vegetation included. ``occupied`` holds gameplay footprints and
    ``near`` their blocking cells inflated by their gap. ``ground`` is the level's terrain grid
    every solid cell must be allowed on. ``held`` is every tile some guard's zone of
    control takes."""

    level: int
    size: tuple[int, int]
    unwalkable: set[Tile]
    occupied: set[Tile]
    near: set[Tile]
    covers: CoverIndex
    avoid: AbstractSet[Tile] = NO_TILES
    barrier: frozenset[Tile] = frozenset()
    ground: Ground = ()
    hemmed: int = 0
    flanked: int = 0
    held: set[Tile] = field(default_factory=set)

    @classmethod
    def build(
        cls,
        level: int,
        grid: Sequence[Sequence[int]],
        objs: Sequence[PlacedObject],
        rules: Sequence[PlacementRule] = (),
    ) -> LevelField:
        barrier = frozenset(
            (x, y) for y, row in enumerate(grid) for x, c in enumerate(row) if Terrain(c).is_barrier
        )
        unwalkable = set(barrier)
        occupied: set[Tile] = set()
        near: set[Tile] = set()
        for o in objs:
            tiles = list(o.footprint.at(o.x, o.y))
            unwalkable.update(t for t, role in tiles if role.blocks)
            if not o.purpose:
                continue
            allc = [t for t, _ch in tiles]
            occupied.update(allc)
            if any(_on_land(grid, t) for t in allc):
                inflate_gap(near, (t for t, ch in tiles if ch in ("B", "X")), GAP)
        size = (len(grid[0]) if grid else 0, len(grid))
        covers = CoverIndex(objs, rules=rules)
        return cls(
            level,
            size,
            unwalkable,
            occupied,
            near,
            covers,
            barrier=barrier,
            ground=grid,
            held=guard_zoc(objs),
        )

    def claim(self, obj: PlacedObject, cells: Iterable[Tile], blk: Iterable[Tile]) -> None:
        cells = list(cells)
        self.covers.add(obj)
        blk = list(blk)
        self.occupied.update(cells)
        inflate_gap(self.near, blk, GAP)
        self.unwalkable.update(blk)

    def walkable(self, t: Tile) -> bool:
        return t not in self.unwalkable

    def closed(self, t: Tile) -> bool:
        return not self.on_map(t) or t in self.unwalkable

    def plant(self, obj: PlacedObject, t: Tile) -> None:
        """Record a one-tile blocking decoration at ``t``: no body may cover it, and it keeps
        no gap."""
        self.covers.add(obj)
        self.occupied.add(t)
        self.unwalkable.add(t)

    def below_share(self) -> bool:
        """Whether hemming one more object keeps the level at or under HEMMED_SHARE."""
        return self.hemmed < HEMMED_SHARE * (self.flanked + 1)

    def accepts(self, obj: PlacedObject) -> bool:
        obj.level = self.level
        return self.covers.accepts(obj)

    def on_map(self, t: Tile) -> bool:
        w, h = self.size
        return 0 <= t[0] < w and 0 <= t[1] < h

    def parts(self, guard: Tile, closing: Iterable[Tile] = ()) -> bool:
        """Whether a guard at ``guard``, with ``closing`` shut too, parts the free land
        into two territories a reader would tell apart."""
        shut = set(closing)

        def free(t: Tile) -> bool:
            return (
                self.on_map(t) and t not in self.unwalkable and t not in self.held and t not in shut
            )

        return splits(zoc_of(guard), free, MIN_AREA)

    def spillable(self, t: Tile) -> bool:
        """A body may cover ``t`` outside its zone: on the map, unwalkable, not water or
        rock."""
        return self.on_map(t) and t in self.unwalkable and t not in self.barrier


def _on_land(grid: Sequence[Sequence[int]], t: Tile) -> bool:
    x, y = t
    return 0 <= y < len(grid) and 0 <= x < len(grid[y]) and grid[y][x] != Terrain.WATER


@dataclass(frozen=True, slots=True)
class SiteZone:
    """What one zone brings to placement: its terrain and that terrain's gameplay
    statistics on the zone's level, its tiles, the entrance bands, the protected web, the open
    tiles left after vegetation and the tiles a hero can walk."""

    terrain: str
    st: TerrainStats
    ts: frozenset[Tile]
    ent_bands: frozenset[Tile]
    prot: frozenset[Tile]
    open_set: frozenset[Tile]
    passable: frozenset[Tile]


@dataclass(frozen=True, slots=True)
class PlacedZone:
    """One zone after placement: its objects, the tiles their footprints cover, their
    approaches, and the open, walkable and protected tiles left for the steps after it."""

    objs: tuple[PlacedObject, ...]
    cells: frozenset[Tile]
    approaches: tuple[Tile, ...]
    open_set: frozenset[Tile]
    passable: frozenset[Tile]
    prot: frozenset[Tile]


@final
class ZoneSite:
    """One zone's placement state after vegetation. ``reserved`` (entrance bands and
    approaches) is off-limits to any footprint; ``reach`` is every tile the web reaches
    through ``passable`` and ``comp`` labels its connected pieces."""

    def __init__(
        self, catalog: Catalog, zid: int, zone: SiteZone, lf: LevelField, seed: int
    ) -> None:
        self.catalog = catalog
        self.guard_probe = catalog.guard(3)
        self.zid = zid
        self.zone = zone
        self.lf = lf
        self.ts: AbstractSet[Tile] = zone.ts
        self.rng = random.Random(seed ^ (zid * 40503) ^ SITE_SALT)
        self.st: TerrainStats = zone.st
        self.reserved: set[Tile] = set(zone.ent_bands)
        self.passable: set[Tile] = set(zone.passable)
        self.prot: set[Tile] = set(zone.prot)
        self.reach: set[Tile] = set()
        self.comp: dict[Tile, int] = {}
        self.set_reach(set(web_dist(self.passable, self.prot)))
        self.objs: list[PlacedObject] = []
        self.cells: set[Tile] = set()
        self.blk: set[Tile] = set()
        self.stranded: set[Tile] = set()
        self.approaches: list[Tile] = []
        self.town_center: tuple[float, float] | None = None
        self.gates: int = 0

    def fit(
        self, ident: Identity, anchor: Tile, mine: bool = False, spill: bool = False
    ) -> Fit | None:
        lf = self.lf
        ts = Spill(self.ts, overlay_cells(ident.footprint, anchor), lf) if spill else self.ts
        fit = fits(ident, anchor, ts, Clearance(lf.occupied, lf.occupied, self.reserved, lf.avoid))
        if fit is None or any(t in lf.near for t in fit[1]):
            return None
        if not stands(self.catalog, ident, anchor, lf.ground):
            return None
        approach = fit[2]
        if approach not in self.reach or not lf.walkable(approach):
            return None
        if not all(lf.walkable(t) for t in door_cells(ident.footprint, anchor)):
            return None
        if mine and not self.guard_fits(ident, fit):
            return None
        return fit

    def guard_fits(self, ident: Identity, fit: Fit) -> bool:
        """Whether a body fitted at ``fit`` keeps its front open and its guard tile legal."""
        return self._front_open(ident, fit) and self.guard_ok(self.guard_tile(ident, fit[2]))

    @staticmethod
    def guard_tile(ident: Identity, approach: Tile) -> Tile:
        return (approach[0], approach[1] + 1) if walk_on_only(ident.footprint) else approach

    def guard_ok(self, tile: Tile) -> bool:
        probe = PlacedObject.at(self.guard_probe, tile, level=self.lf.level, purpose=Purpose.GUARD)
        return self.lf.accepts(probe)

    def _front_open(self, ident: Identity, fit: Fit) -> bool:
        appr = fit[2]
        behind = [
            (appr[0], appr[1] + k) for k in range(1, 3 if walk_on_only(ident.footprint) else 2)
        ]
        return all(
            t in self.ts
            and t not in self.lf.occupied
            and t not in fit[1]
            and t in self.reach
            and self.lf.walkable(t)
            for t in behind
        )

    def cover(self, ident: Identity, anchor: Tile) -> int:
        """How well a sprite at ``anchor`` rests against closed tiles: its back score plus
        FLANK_WEIGHT per closed flank."""
        cells = [t for t, _role in ident.footprint.at(*anchor)]
        back = back_score(ident.footprint, anchor, self.lf.unwalkable, self.lf.size)
        return back + FLANK_WEIGHT * closed_flanks(cells, self.lf.closed)

    def snug(self, ident: Identity, anchor: Tile) -> bool:
        """Whether a sprite at ``anchor`` sits snug for its size."""
        return snug(ident.footprint, anchor, self.lf.closed)

    def in_field(self, ident: Identity, anchor: Tile) -> bool:
        """Whether a sprite at ``anchor`` stands in the field, clear of every closed tile."""
        return in_field(ident.footprint, anchor, self.lf.closed)

    def sided(self, ident: Identity, anchor: Tile) -> bool:
        """Whether a sprite at ``anchor`` rests against a closed tile, corners included."""
        return sided(ident.footprint, anchor, self.lf.closed)

    def set_reach(self, reach: set[Tile]) -> None:
        self.reach = reach
        self.comp = components(reach)

    def reach_without(self, blk: Iterable[Tile], spare: int = 0) -> set[Tile] | None:
        cut = set(blk) & self.reach
        left = self.reach - cut
        if not cut:
            return left
        after = components(left)
        webbed = {after[t] for t in self.prot - cut if t in left}
        kept: dict[int, int] = {}
        stranded: set[Tile] = set()
        for t in left:
            if after[t] not in webbed:
                stranded.add(t)
            elif kept.setdefault(self.comp[t], after[t]) != after[t]:
                return None
        if len(stranded) > spare or stranded & self.reserved:
            return None
        return left - stranded

    def detours(self, blk: Iterable[Tile]) -> bool:
        return detours(blk, lambda t: not self.lf.closed(t))

    def block(self, blk: Iterable[Tile], reach: set[Tile]) -> None:
        cut = set(blk)
        self.stranded |= self.reach - cut - reach
        self.blk.update(cut)
        self.passable -= cut | self.stranded
        if cut & self.prot:
            self.prot = mend(self.prot, cut, self.passable)
        self.set_reach(reach)

    def nearest_order(self, cx: float, cy: float) -> list[Tile]:
        return sorted(self.ts, key=lambda t: ((t[0] - cx) ** 2 + (t[1] - cy) ** 2, t))

    def centroid_order(self, ident: Identity) -> list[Tile]:
        area = len(self.ts)
        mh = ident.footprint.height
        mw = ident.footprint.width
        ccx = sum(t[0] for t in self.ts) / area + (mw - 1) / 2.0
        ccy = sum(t[1] for t in self.ts) / area + (mh - 1) / 2.0
        return self.nearest_order(ccx, ccy)

    def place(
        self,
        purpose: str,
        ident: Identity,
        centres: Iterable[Tile],
        footing: Footing | None = None,
        guard: int | None = None,
    ) -> PlacedObject | None:
        footing = footing_of(purpose) if footing is None else footing
        legal: dict[Tile, Fit | None] = {}
        rejected: set[Tile] = set()
        covers: dict[Tile, int] = {}
        for c in centres:
            window = [(c[0] + dx, c[1] + dy) for dx, dy in _WINDOW]
            for t in window:
                if t not in legal:
                    legal[t] = spot(self, footing, ident, t)
            near = [t for t in window if legal[t] is not None and t not in rejected]
            for t in near:
                if t not in covers:
                    covers[t] = self.cover(ident, t)
            near.sort(key=lambda t: (-covers[t], cheb(t, c), t))
            for t in near:
                fit = legal[t]
                assert fit is not None
                obj = self.try_commit(purpose, ident, t, fit, guard)
                if obj is not None:
                    return obj
                rejected.add(t)
        return None

    def try_commit(
        self, purpose: str, ident: Identity, anchor: Tile, fit: Fit, guard: int | None = None
    ) -> PlacedObject | None:
        obj = PlacedObject.at(
            ident, anchor, level=self.lf.level, purpose=purpose, payload=payload_for(purpose)
        )
        if not self.lf.accepts(obj) or self.detours(fit[1]):
            return None
        guarded = purpose == Purpose.MINE if guard is None else guard > 0
        if guarded and self.lf.parts(self.guard_tile(ident, fit[2]), fit[1]):
            return None
        reach = self.reach_without(fit[1])
        if reach is None:
            return None
        self.commit(obj, fit, reach, guard)
        return obj

    def commit(
        self, obj: PlacedObject, fit: Fit, reach: set[Tile], guard: int | None = None
    ) -> None:
        allc, blk, approach = fit
        self.lf.claim(obj, allc, blk)
        self.objs.append(obj)
        self.cells.update(allc)
        self.block(blk, reach)
        self.approaches.append(approach)
        self.reserved.add(approach)
        start = approach
        level = self._mine_guard(obj) if guard is None and obj.purpose == Purpose.MINE else guard
        if level:
            start = self._guarded_front(obj, approach, level)
        if obj.purpose == Purpose.TOWN:
            mh = obj.footprint.height
            mw = obj.footprint.width
            self.town_center = (obj.x - (mw - 1) / 2.0, obj.y - (mh - 1) / 2.0)
        self.link(start)
        if obj.purpose in FLANKED:
            self._hem(obj)

    def _hem(self, obj: PlacedObject) -> None:
        lf = self.lf
        sides = flank_tiles(t for t, _role in obj.footprint.at(obj.x, obj.y))
        if lf.below_share():
            for side in sides:
                if not any(lf.closed(t) for t in side):
                    _ = any(self._plant(t) for t in side)
        lf.flanked += 1
        lf.hemmed += all(any(lf.closed(t) for t in side) for side in sides)

    def _plant(self, t: Tile) -> bool:
        if not self._plantable(t):
            return False
        pool = [
            i
            for i in self.catalog.decor(self.zone.terrain, blocking=True, max_cells=1)
            if stands(self.catalog, i, t, self.lf.ground)
        ]
        if not pool:
            return False
        plant = PlacedObject.at(self.rng.choice(pool), t, level=self.lf.level, purpose="")
        if not self.lf.accepts(plant) or self.detours([t]):
            return False
        reach = self.reach_without([t])
        if reach is None:
            return False
        self.lf.plant(plant, t)
        self.objs.append(plant)
        self.cells.add(t)
        self.block([t], reach)
        return True

    def link(self, start: Tile) -> None:
        self.prot.update(path_to_web(start, self.prot, self.passable))

    def _guarded_front(self, obj: PlacedObject, approach: Tile, level: int) -> Tile:
        if walk_on_only(obj.footprint):
            approach = (approach[0], approach[1] + 1)
            self.approaches.append(approach)
        tail = (approach[0], approach[1] + 1)
        self.approaches.append(tail)
        self.reserved.update((approach, tail))
        self._guard_front(approach, level)
        return tail

    def add_guard(self, ident: Identity, tile: Tile) -> PlacedObject:
        guard = PlacedObject.at(
            ident,
            tile,
            level=self.lf.level,
            purpose=Purpose.GUARD,
            payload=Guard(),
        )
        self.lf.covers.add(guard)
        self.lf.occupied.add(tile)
        self.lf.held.update(zoc_of(tile))
        self.objs.append(guard)
        self.cells.add(tile)
        return guard

    def _mine_guard(self, mine: PlacedObject) -> int:
        subtype = str(self.catalog.identity_of(mine.kind).subtype)
        lvl = MINE_GUARD_LVL.get(subtype, 3)
        if subtype not in ("sawmill", "orePit") and self.rng.random() < 0.25:
            lvl += 1
        return lvl

    def _guard_front(self, approach: Tile, level: int) -> None:
        _ = self.add_guard(self.catalog.guard(level), approach)
        ex, ey = approach[0], approach[1] - 1
        seal_pool = self.catalog.decor(self.zone.terrain, blocking=True, max_cells=1)
        if not seal_pool:
            return
        for s in ((ex - 1, ey), (ex + 1, ey), (ex - 1, ey + 1), (ex + 1, ey + 1)):
            pool = [i for i in seal_pool if stands(self.catalog, i, s, self.lf.ground)]
            if pool and self._sealable(s):
                self._seal(self.rng.choice(pool), s)

    def _plantable(self, t: Tile) -> bool:
        return (
            t in self.ts
            and t not in self.lf.occupied
            and t not in self.lf.avoid
            and t not in self.zone.ent_bands
            and t not in self.approaches
            and self.lf.walkable(t)
        )

    def _sealable(self, s: Tile) -> bool:
        return (
            s in self.ts
            and s not in self.lf.occupied
            and s not in self.lf.avoid
            and s not in self.reserved
            and self.lf.walkable(s)
        )

    def _seal(self, ident: Identity, s: Tile) -> None:
        seal = PlacedObject.at(ident, s, level=self.lf.level, purpose=Purpose.MINE_SEAL)
        if not self.lf.accepts(seal):
            return
        reach = self.reach_without([s])
        if reach is None:
            return
        self.lf.claim(seal, [s], [s])
        self.objs.append(seal)
        self.cells.add(s)
        self.block([s], reach)

    def placed(self) -> PlacedZone:
        cells = frozenset(self.cells)
        solid = frozenset(
            t for o in self.objs for t, role in o.footprint.at(o.x, o.y) if role is not Role.OVERLAY
        )
        return PlacedZone(
            tuple(self.objs),
            cells,
            tuple(self.approaches),
            self.zone.open_set - solid - frozenset(self.approaches),
            self.zone.passable - self.blk - self.stranded,
            frozenset(self.prot),
        )


@dataclass(slots=True)
class SiteIndex:
    """The zone sites of one level, and which zone owns each tile."""

    lf: LevelField
    sites: dict[int, ZoneSite] = field(default_factory=dict)
    zone_of: dict[Tile, int] = field(default_factory=dict)

    def site_at(self, t: Tile) -> ZoneSite | None:
        zid = self.zone_of.get(t)
        return None if zid is None else self.sites.get(zid)


class Footing(Protocol):
    """Whether a zone site tries an anchor for an object, and whether its body may stand there."""

    def admits(self, site: ZoneSite, ident: Identity, anchor: Tile) -> bool: ...

    def fit(self, site: ZoneSite, ident: Identity, anchor: Tile) -> Fit | None: ...


@final
@dataclass(frozen=True, slots=True)
class Spill:
    """The zone's tiles, the spillable land outside it, and the sprite's ``overlay`` cells
    anywhere, past the map's edge too."""

    ts: AbstractSet[Tile]
    overlay: AbstractSet[Tile]
    lf: LevelField

    def __contains__(self, t: object) -> bool:
        return t in self.ts or t in self.overlay or self.lf.spillable(cast(Tile, t))


@dataclass(frozen=True, slots=True)
class ZoneFooting:
    """The body inside the zone, clear of the gap around other bodies, off the entrance bands
    and earlier approaches. A mine also keeps its front open and its guard tile legal. With
    ``spill``, the body may also cover spillable land outside the zone, and the sprite's
    overlay cells may lie anywhere, past the map's edge too."""

    mine: bool = False
    spill: bool = False

    def admits(self, site: ZoneSite, ident: Identity, anchor: Tile) -> bool:
        _ = ident
        return anchor in site.ts

    def fit(self, site: ZoneSite, ident: Identity, anchor: Tile) -> Fit | None:
        return site.fit(ident, anchor, self.mine, self.spill)


@final
@dataclass(frozen=True, slots=True)
class TownFooting:
    """A town's body off other bodies, earlier approaches and avoided tiles, each cell in the
    zone or on spillable land. Its entrance and approach are walkable and its approach stands
    in the zone, reached from the web. It may cover the entrance bands and keeps no gap. With
    ``loose_overlay``, the sprite's overlay cells block nothing, so outside the zone they may
    lie anywhere on the map."""

    loose_overlay: bool = False

    def admits(self, site: ZoneSite, ident: Identity, anchor: Tile) -> bool:
        fw, fh = ident.footprint.width, ident.footprint.height
        x, y = anchor
        return any((x - dx, y - dy) in site.ts for dx in range(fw) for dy in range(fh))

    def fit(self, site: ZoneSite, ident: Identity, anchor: Tile) -> Fit | None:
        lf = site.lf
        allc, blk, approach = footprint_cells(ident.footprint, *anchor)
        if approach is None:
            return None
        hard = set(site.approaches) | lf.avoid
        loose = overlay_cells(ident.footprint, anchor) if self.loose_overlay else NO_TILES
        if any(
            c in lf.occupied
            or c in hard
            or (c not in site.ts and not lf.spillable(c) and not (c in loose and lf.on_map(c)))
            for c in allc
        ):
            return None
        if approach not in site.ts or approach in lf.occupied or approach in blk:
            return None
        if approach in lf.avoid or approach not in site.reach or not lf.walkable(approach):
            return None
        if not all(lf.walkable(t) for t in door_cells(ident.footprint, anchor)):
            return None
        return allc, blk, approach


@final
@dataclass(frozen=True, slots=True)
class SnugFooting:
    """Another footing's spots, kept to those where the sprite sits snug for its size."""

    inner: Footing

    def admits(self, site: ZoneSite, ident: Identity, anchor: Tile) -> bool:
        return self.inner.admits(site, ident, anchor)

    def fit(self, site: ZoneSite, ident: Identity, anchor: Tile) -> Fit | None:
        fit = self.inner.fit(site, ident, anchor)
        return fit if fit is not None and site.snug(ident, anchor) else None


@final
@dataclass(frozen=True, slots=True)
class SidedFooting:
    """Another footing's spots, kept to those where a closed tile lies on or around the sprite."""

    inner: Footing

    def admits(self, site: ZoneSite, ident: Identity, anchor: Tile) -> bool:
        return self.inner.admits(site, ident, anchor)

    def fit(self, site: ZoneSite, ident: Identity, anchor: Tile) -> Fit | None:
        fit = self.inner.fit(site, ident, anchor)
        return fit if fit is not None and site.sided(ident, anchor) else None


@final
@dataclass(frozen=True, slots=True)
class GuardedFooting:
    """Another footing's spots, kept to those with an open front and a legal guard tile."""

    inner: Footing

    def admits(self, site: ZoneSite, ident: Identity, anchor: Tile) -> bool:
        return self.inner.admits(site, ident, anchor)

    def fit(self, site: ZoneSite, ident: Identity, anchor: Tile) -> Fit | None:
        fit = self.inner.fit(site, ident, anchor)
        return fit if fit is not None and site.guard_fits(ident, fit) else None


@final
@dataclass(frozen=True, slots=True)
class OpenFooting:
    """Another footing's spots in the field, where no closed tile touches the sprite."""

    inner: Footing

    def admits(self, site: ZoneSite, ident: Identity, anchor: Tile) -> bool:
        return self.inner.admits(site, ident, anchor) and site.in_field(ident, anchor)

    def fit(self, site: ZoneSite, ident: Identity, anchor: Tile) -> Fit | None:
        return self.inner.fit(site, ident, anchor)


def large(ident: Identity) -> bool:
    """Whether ``ident`` has a body of the largest size class."""
    return size_class(ident.footprint) == SIZE_CLASSES[-1]


def openness(site: ZoneSite, centre: Tile, r: int) -> int:
    """The open tiles within ``r`` of ``centre`` on the site's level."""
    x, y = centre
    return sum(
        not site.lf.closed((x + dx, y + dy)) for dx in range(-r, r + 1) for dy in range(-r, r + 1)
    )


def spot(site: ZoneSite, footing: Footing, ident: Identity, anchor: Tile) -> Fit | None:
    """The fit of ``ident`` at ``anchor`` under ``footing``, None when the footing does not
    try that anchor or the body does not stand there."""
    return footing.fit(site, ident, anchor) if footing.admits(site, ident, anchor) else None


def footing_of(purpose: str) -> Footing:
    """The footing an object of ``purpose`` stands on."""
    return FOOTINGS.get(purpose, ZONE_FOOTING)


def guarded_footing_of(purpose: str) -> Footing:
    """The footing an object of ``purpose`` stands on with a guard at its door."""
    return GUARDED_FOOTINGS.get(purpose, MINE_FOOTING)


def footing_for(purpose: str, guard: int) -> Footing:
    """The footing an object of ``purpose`` stands on behind a guard of level ``guard``, with
    no guard at its door at level 0, a mine included."""
    if guard:
        return guarded_footing_of(purpose)
    return HOME_FOOTING if purpose == Purpose.TOWN else ZONE_FOOTING


ZONE_FOOTING = ZoneFooting()
HOME_FOOTING = TownFooting(loose_overlay=True)
MINE_FOOTING = ZoneFooting(mine=True)
SUPPLY_FOOTING = ZoneFooting(mine=True, spill=True)
FOOTINGS: dict[str, Footing] = {Purpose.TOWN: HOME_FOOTING, Purpose.MINE: MINE_FOOTING}
GUARDED_FOOTINGS: dict[str, Footing] = {Purpose.TOWN: GuardedFooting(HOME_FOOTING)}

"""Gameplay spots against the vegetated field: one ``LevelField`` per level holds what every
zone shares (unwalkable tiles, gameplay footprints, the cover index, the terrain rule), one
``ZoneSite`` per zone finds and commits a spot for each object.

A spot is legal when the footprint fits the zone clear of other gameplay footprints, with its
blocking cells GAP tiles away from theirs, and off the entrance bands and earlier approaches;
the entrance and its approach are walkable and
reachable from the web; and the blocking cells split no reachable area in two. Blocking cells
may land on vegetation, the zone rim and the web, and the web then walks around them. Among
the legal anchors of a neighbourhood the one whose sprite top rests most against unwalkable
tiles wins."""

from __future__ import annotations

import collections
import math
import random
from collections.abc import Callable, Iterable, Iterator, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from typing import final

from vcmi_mapgen.core.grid.components import STEPS4, components
from vcmi_mapgen.core.grid.geometry import edge_dist
from vcmi_mapgen.core.model import CoverIndex, Identity, JsonValue, PlacedObject, Tile
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.pipeline import ZoneWorkspace
from vcmi_mapgen.core.steps.gameplay.mines import (
    CORE_SPELLS,
    MINE_GUARD_LVL,
    Covariates,
    TerrainStats,
    gate_dist,
    intensity_weights,
    load_gameplay,
    openness,
)
from vcmi_mapgen.core.steps.gate.gates import (
    NO_TILES,
    Clearance,
    Fit,
    fits,
    inflate_gap,
    rnd_monster,
)
from vcmi_mapgen.core.steps.placement import web_dist
from vcmi_mapgen.vcmi.catalog import decor as DC
from vcmi_mapgen.vcmi.catalog.decor import EXCLUDE_DECOR_TYPES

SITE_SALT = 0xA77A
NEIGHBOURHOOD = 3
MIN_WEIGHT = 1e-300
TOWN_OPTIONS: dict[str, JsonValue] = {
    "buildings": {"allOf": ["core:fort", "core:tavern", "core:dwellingLvl1", "core:dwellingLvl2"]},
    "possibleSpells": CORE_SPELLS,
}
GUARD_OPTIONS: dict[str, JsonValue] = {"character": "hostile"}
GUARD_PROBE = rnd_monster(3)


def mask_tiles(mask: Sequence[str], anchor: Tile) -> Iterator[tuple[Tile, str]]:
    hh = len(mask)
    for r, row in enumerate(mask):
        ww = len(row)
        for c, ch in enumerate(row):
            if ch != " ":
                yield (anchor[0] - (ww - 1 - c), anchor[1] - (hh - 1 - r)), ch


def back_score(
    ident: Identity, anchor: Tile, unwalkable: AbstractSet[Tile], size: tuple[int, int]
) -> int:
    """Per sprite column, the topmost drawn tile scores 1 when it is unwalkable and 1 more
    when the tile above it is. Off-map counts as unwalkable. A 1-tile object scores 0."""
    cells = [t for t, _ch in mask_tiles(ident.mask, anchor)]
    if len(cells) < 2:
        return 0
    top: dict[int, int] = {}
    for x, y in cells:
        top[x] = min(y, top.get(x, y))
    w, h = size

    def bad(x: int, y: int) -> int:
        return int(not (0 <= x < w and 0 <= y < h) or (x, y) in unwalkable)

    return sum(bad(x, y) + bad(x, y - 1) for x, y in top.items())


def door_cells(ident: Identity, anchor: Tile) -> list[Tile]:
    return [t for t, ch in mask_tiles(ident.mask, anchor) if ch in ("X", "A")]


def walk_on_only(mask: Sequence[str]) -> bool:
    return not any("X" in row for row in mask)


def path_to_web(start: Tile, web: AbstractSet[Tile], passable: AbstractSet[Tile]) -> list[Tile]:
    """The shortest 4-connected walk from ``start`` to the nearest web tile, both ends
    included, or an empty list when none exists."""
    prev: dict[Tile, Tile | None] = {start: None}
    q = collections.deque([start])
    while q:
        cur = q.popleft()
        if cur in web:
            path: list[Tile] = []
            node: Tile | None = cur
            while node is not None:
                path.append(node)
                node = prev[node]
            return path
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (cur[0] + dx, cur[1] + dy)
            if n in passable and n not in prev:
                prev[n] = cur
                q.append(n)
    return []


def _walk(src: AbstractSet[Tile], dst: AbstractSet[Tile], passable: AbstractSet[Tile]) -> set[Tile]:
    prev: dict[Tile, Tile | None] = dict.fromkeys(sorted(src))
    q = collections.deque(prev)
    while q:
        cur = q.popleft()
        if cur in dst:
            path: set[Tile] = set()
            node: Tile | None = cur
            while node is not None:
                path.add(node)
                node = prev[node]
            return path
        for dx, dy in STEPS4:
            n = (cur[0] + dx, cur[1] + dy)
            if n in passable and n not in prev:
                prev[n] = cur
                q.append(n)
    return set()


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


def options_for(purpose: str) -> dict[str, JsonValue] | None:
    if purpose == "GUARD":
        return dict(GUARD_OPTIONS)
    if purpose == "TOWN":
        return dict(TOWN_OPTIONS)
    return None


def cheb(a: Tile, b: Tile) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


@dataclass(slots=True)
class LevelField:
    """What every zone of one level shares. ``unwalkable`` is water, rock and every blocking
    cell on the level, vegetation included. ``occupied`` holds gameplay footprints and
    ``near`` their blocking cells inflated by GAP. ``legal`` is the terrain rule."""

    level: int
    size: tuple[int, int]
    unwalkable: set[Tile]
    occupied: set[Tile]
    near: set[Tile]
    covers: CoverIndex
    legal: Callable[[PlacedObject], bool]
    avoid: AbstractSet[Tile] = NO_TILES

    @classmethod
    def build(
        cls,
        level: int,
        grid: Sequence[Sequence[int]],
        objs: Sequence[PlacedObject],
        legal: Callable[[PlacedObject], bool],
    ) -> LevelField:
        unwalkable = {
            (x, y) for y, row in enumerate(grid) for x, c in enumerate(row) if Terrain(c).is_barrier
        }
        occupied: set[Tile] = set()
        near: set[Tile] = set()
        for o in objs:
            tiles = list(mask_tiles(o.mask, (o.x, o.y)))
            unwalkable.update(t for t, ch in tiles if ch in ("B", "X"))
            if not o.purpose:
                continue
            allc = [t for t, _ch in tiles]
            occupied.update(allc)
            if any(_on_land(grid, t) for t in allc):
                inflate_gap(near, (t for t, ch in tiles if ch in ("B", "X")))
        size = (len(grid[0]) if grid else 0, len(grid))
        return cls(level, size, unwalkable, occupied, near, CoverIndex(objs), legal)

    def claim(self, obj: PlacedObject, cells: Iterable[Tile], blk: Iterable[Tile]) -> None:
        cells = list(cells)
        self.covers.add(obj)
        blk = list(blk)
        self.occupied.update(cells)
        inflate_gap(self.near, blk)
        self.unwalkable.update(blk)

    def walkable(self, t: Tile) -> bool:
        return t not in self.unwalkable

    def accepts(self, obj: PlacedObject) -> bool:
        obj.level = self.level
        return self.covers.accepts(obj) and self.legal(obj)


def _on_land(grid: Sequence[Sequence[int]], t: Tile) -> bool:
    x, y = t
    return 0 <= y < len(grid) and 0 <= x < len(grid[y]) and grid[y][x] != Terrain.WATER


@final
class ZoneSite:
    """One zone's placement state after vegetation. ``reserved`` (entrance bands and
    approaches) is off-limits to any footprint; ``reach`` is every tile the web reaches
    through ``passable`` and ``comp`` labels its connected pieces."""

    def __init__(self, zid: int, zw: ZoneWorkspace, lf: LevelField, seed: int) -> None:
        self.zid = zid
        self.zw = zw
        self.lf = lf
        self.ts: AbstractSet[Tile] = zw.ts
        self.rng = random.Random(seed ^ (zid * 40503) ^ SITE_SALT)
        self.st: TerrainStats = load_gameplay(level=lf.level)[zw.terrain]
        self.reserved: set[Tile] = set(zw.ent_bands) | set(zw.approaches)
        self.passable: set[Tile] = set(zw.passable)
        self.prot: set[Tile] = set(zw.prot)
        self.reach: set[Tile] = set()
        self.comp: dict[Tile, int] = {}
        self.set_reach(set(web_dist(self.passable, self.prot)))
        self.cov = Covariates(
            edge_dist(zw.ts), gate_dist(zw.ts, zw.ent_bands), openness(zw.open_set)
        )
        self.wcache: dict[str, dict[Tile, float]] = {}
        self.objs: list[PlacedObject] = []
        self.cells: set[Tile] = set()
        self.blk: set[Tile] = set()
        self.stranded: set[Tile] = set()
        self.approaches: list[Tile] = []
        self.town_center: tuple[float, float] | None = None
        self.spent: int = 0
        self.gates: int = 0

    def fit(self, ident: Identity, anchor: Tile, mine: bool = False) -> Fit | None:
        lf = self.lf
        fit = fits(
            ident, anchor, self.ts, Clearance(lf.occupied, lf.occupied, self.reserved, lf.avoid)
        )
        if fit is None or any(t in lf.near for t in fit[1]):
            return None
        approach = fit[2]
        if approach not in self.reach or not lf.walkable(approach):
            return None
        if not all(lf.walkable(t) for t in door_cells(ident, anchor)):
            return None
        if mine and not self._front_open(ident, fit):
            return None
        if mine and not self.guard_ok(self._guard_tile(ident, approach)):
            return None
        return fit

    @staticmethod
    def _guard_tile(ident: Identity, approach: Tile) -> Tile:
        return (approach[0], approach[1] + 1) if walk_on_only(ident.mask) else approach

    def guard_ok(self, tile: Tile) -> bool:
        probe = PlacedObject.at(GUARD_PROBE, tile, level=self.lf.level, purpose="GUARD")
        return self.lf.accepts(probe)

    def _front_open(self, ident: Identity, fit: Fit) -> bool:
        appr = fit[2]
        behind = [(appr[0], appr[1] + k) for k in range(1, 3 if walk_on_only(ident.mask) else 2)]
        return all(
            t in self.ts
            and t not in self.lf.occupied
            and t not in fit[1]
            and t in self.reach
            and self.lf.walkable(t)
            for t in behind
        )

    def back(self, ident: Identity, anchor: Tile) -> int:
        return back_score(ident, anchor, self.lf.unwalkable, self.lf.size)

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

    def block(self, blk: Iterable[Tile], reach: set[Tile]) -> None:
        cut = set(blk)
        self.stranded |= self.reach - cut - reach
        self.blk.update(cut)
        self.passable -= cut | self.stranded
        if cut & self.prot:
            self.prot = mend(self.prot, cut, self.passable)
        self.set_reach(reach)

    def intensity_order(self, purpose: str) -> list[Tile]:
        if purpose not in self.wcache:
            self.wcache[purpose] = intensity_weights(self.ts, purpose, self.st, self.cov)
        w = self.wcache[purpose]
        keys = {t: es_key(self.rng, w[t]) for t in sorted(self.ts)}
        return sorted(keys, key=lambda t: (-keys[t], t))

    def nearest_order(self, cx: float, cy: float) -> list[Tile]:
        return sorted(self.ts, key=lambda t: ((t[0] - cx) ** 2 + (t[1] - cy) ** 2, t))

    def centroid_order(self, ident: Identity) -> list[Tile]:
        area = len(self.ts)
        mh = len(ident.mask)
        mw = max(len(r) for r in ident.mask)
        ccx = sum(t[0] for t in self.ts) / area + (mw - 1) / 2.0
        ccy = sum(t[1] for t in self.ts) / area + (mh - 1) / 2.0
        return self.nearest_order(ccx, ccy)

    def place(self, purpose: str, ident: Identity, centres: Iterable[Tile]) -> PlacedObject | None:
        mine = purpose == "MINE"
        legal = {t: f for t in sorted(self.ts) if (f := self.fit(ident, t, mine)) is not None}
        rejected: set[Tile] = set()
        backs: dict[Tile, int] = {}
        for c in centres:
            if len(rejected) == len(legal):
                return None
            window = [
                (c[0] + dx, c[1] + dy)
                for dx in range(-NEIGHBOURHOOD, NEIGHBOURHOOD + 1)
                for dy in range(-NEIGHBOURHOOD, NEIGHBOURHOOD + 1)
            ]
            near = [t for t in window if t in legal and t not in rejected]
            for t in near:
                if t not in backs:
                    backs[t] = self.back(ident, t)
            near.sort(key=lambda t: (-backs[t], cheb(t, c), t))
            for t in near:
                obj = self.try_commit(purpose, ident, t, legal[t])
                if obj is not None:
                    return obj
                rejected.add(t)
        return None

    def try_commit(
        self, purpose: str, ident: Identity, anchor: Tile, fit: Fit
    ) -> PlacedObject | None:
        obj = PlacedObject.at(
            ident, anchor, level=self.lf.level, purpose=purpose, options=options_for(purpose)
        )
        if not self.lf.accepts(obj):
            return None
        reach = self.reach_without(fit[1])
        if reach is None:
            return None
        self.commit(obj, fit, reach)
        return obj

    def commit(self, obj: PlacedObject, fit: Fit, reach: set[Tile]) -> None:
        allc, blk, approach = fit
        self.lf.claim(obj, allc, blk)
        self.objs.append(obj)
        self.cells.update(allc)
        self.block(blk, reach)
        self.approaches.append(approach)
        self.reserved.add(approach)
        start = approach
        if obj.purpose == "MINE":
            start = self._mine_front(obj, approach)
        elif obj.purpose == "TOWN":
            mh = len(obj.mask)
            mw = max(len(r) for r in obj.mask)
            self.town_center = (obj.x - (mw - 1) / 2.0, obj.y - (mh - 1) / 2.0)
        self.link(start)

    def link(self, start: Tile) -> None:
        self.prot.update(path_to_web(start, self.prot, self.passable))

    def _mine_front(self, obj: PlacedObject, approach: Tile) -> Tile:
        if walk_on_only(obj.mask):
            approach = (approach[0], approach[1] + 1)
            self.approaches.append(approach)
        tail = (approach[0], approach[1] + 1)
        self.approaches.append(tail)
        self.reserved.update((approach, tail))
        self._guard_mine(obj, approach)
        return tail

    def add_guard(self, ident: Identity, tile: Tile) -> PlacedObject:
        guard = PlacedObject.at(
            ident, tile, level=self.lf.level, purpose="GUARD", options=options_for("GUARD")
        )
        self.lf.covers.add(guard)
        self.lf.occupied.add(tile)
        self.objs.append(guard)
        self.cells.add(tile)
        return guard

    def _guard_mine(self, mine: PlacedObject, approach: Tile) -> None:
        subtype = str(mine.subtype)
        lvl = MINE_GUARD_LVL.get(subtype, 3)
        if subtype not in ("sawmill", "orePit") and self.rng.random() < 0.25:
            lvl += 1
        _ = self.add_guard(rnd_monster(lvl), approach)
        ex, ey = approach[0], approach[1] - 1
        seal_pool = DC.decor_pool(
            self.zw.terrain, blocking=True, max_cells=1, exclude_types=EXCLUDE_DECOR_TYPES
        )
        if not seal_pool:
            return
        for s in ((ex - 1, ey), (ex + 1, ey), (ex - 1, ey + 1), (ex + 1, ey + 1)):
            if self._sealable(s):
                self._seal(self.rng.choice(seal_pool), s)

    def _sealable(self, s: Tile) -> bool:
        return (
            s in self.ts
            and s not in self.lf.occupied
            and s not in self.lf.avoid
            and s not in self.reserved
            and self.lf.walkable(s)
        )

    def _seal(self, ident: Identity, s: Tile) -> None:
        seal = PlacedObject.at(ident, s, level=self.lf.level, purpose="MINE_SEAL")
        if not self.lf.accepts(seal):
            return
        reach = self.reach_without([s])
        if reach is None:
            return
        self.lf.claim(seal, [s], [s])
        self.objs.append(seal)
        self.cells.add(s)
        self.block([s], reach)

    def write_back(self) -> None:
        zw = self.zw
        zw.gobjs.extend(self.objs)
        zw.occupied = zw.occupied | frozenset(self.cells)
        zw.gblocked = zw.gblocked | frozenset(self.blk)
        zw.approaches = (*zw.approaches, *self.approaches)
        zw.open_set = zw.open_set - self.cells - frozenset(self.approaches)
        zw.passable = zw.passable - self.blk - self.stranded
        zw.prot = frozenset(self.prot)


@dataclass(slots=True)
class SiteIndex:
    """The zone sites of one level, and which zone owns each tile."""

    lf: LevelField
    sites: dict[int, ZoneSite] = field(default_factory=dict)
    zone_of: dict[Tile, int] = field(default_factory=dict)

    def site_at(self, t: Tile) -> ZoneSite | None:
        zid = self.zone_of.get(t)
        return None if zid is None else self.sites.get(zid)

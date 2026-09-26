"""Attractions: the dwellings, banks and visitables TownsStep planned for each zone,
emitted once vegetation has grown around their reserved spots. A planned spot the cover
index or the terrain rule refuses falls back to a fresh spot next to vegetation that keeps
its approach reachable from the zone's walkable web and never cuts the zone's walkable
field in two."""

from __future__ import annotations

import collections
import math
import random
from collections.abc import Callable, Iterable, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import final

from vcmi_mapgen.kit.geometry import NB8, edge_dist
from vcmi_mapgen.models import CoverIndex, Identity, PlacedObject, Tile
from vcmi_mapgen.pipeline import ZoneWorkspace
from vcmi_mapgen.steps.gameplay.mines import (
    Covariates,
    gate_dist,
    intensity_weights,
    mine_gameplay,
    openness,
    tie_dwellings,
)
from vcmi_mapgen.steps.gate.gates import Clearance, Fit, fits, inflate_gap
from vcmi_mapgen.steps.placement import web_dist

ATTRACT_SALT = 0xA77A
ADJ_FLOOR = 0.05
MIN_WEIGHT = 1e-300


@dataclass(frozen=True, slots=True)
class LevelField:
    """What one level offers every zone's attractions: the tiles objects already cover,
    the extra tiles no footprint may take (seaport approaches), the tunnel cells nothing
    may touch, the level's cover index and the terrain rule every object must pass."""

    level: int
    seed: int
    taken: AbstractSet[Tile]
    reserved: AbstractSet[Tile]
    avoid: AbstractSet[Tile]
    covers: CoverIndex
    legal: Callable[[PlacedObject], bool]


def _path_to_web(start: Tile, web: AbstractSet[Tile], passable: AbstractSet[Tile]) -> list[Tile]:
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


def _es_key(rng: random.Random, weight: float) -> float:
    return math.log(1.0 - rng.random()) / max(weight, MIN_WEIGHT)


@final
class _ZoneAttractions:
    def __init__(self, zid: int, zw: ZoneWorkspace, lf: LevelField) -> None:
        self.zw = zw
        self.lf = lf
        self.rng = random.Random(lf.seed ^ (zid * 40503) ^ ATTRACT_SALT)
        self.st = mine_gameplay(level=lf.level)[zw.terrain]
        self.cov = Covariates(
            edge_dist(zw.ts), gate_dist(zw.ts, zw.ent_bands), openness(zw.open_set)
        )
        self.occupied: set[Tile] = set(zw.occupied) | set(lf.taken)
        self.near: set[Tile] = set(lf.taken)
        inflate_gap(self.near, zw.occupied)
        self.reserved: set[Tile] = set(zw.rim8 | zw.ent_bands | zw.prot | lf.reserved) | set(
            zw.approaches
        )
        self.passable: set[Tile] = set(zw.passable)
        self.prot: set[Tile] = set(zw.prot)
        self.reach: set[Tile] = set(web_dist(self.passable, self.prot))
        self.objs: list[PlacedObject] = []
        self.cells: set[Tile] = set()
        self.blk: set[Tile] = set()
        self.approaches: list[Tile] = []

    def _fitting(self, ident: Identity) -> list[tuple[Tile, Fit]]:
        clear = Clearance(self.occupied, self.near, self.reserved, self.lf.avoid)
        out: list[tuple[Tile, Fit]] = []
        for t in sorted(self.zw.ts):
            fit = fits(ident, t, self.zw.ts, clear)
            if fit is not None and fit[2] in self.reach:
                out.append((t, fit))
        return out

    def _adjacency(self, cells: Sequence[Tile]) -> int:
        own = set(cells)
        ring = {(x + dx, y + dy) for x, y in cells for dx, dy in NB8} - own
        return len(ring & self.zw.blocked)

    def _ranked(self, purpose: str, cands: Sequence[tuple[Tile, Fit]]) -> list[tuple[Tile, Fit]]:
        w = intensity_weights((t for t, _f in cands), purpose, self.st, self.cov)
        keyed = [
            (_es_key(self.rng, w[t] * (self._adjacency(fit[0]) + ADJ_FLOOR)), t, fit)
            for t, fit in cands
        ]
        keyed.sort(key=lambda k: (-k[0], k[1]))
        return [(t, fit) for _k, t, fit in keyed]

    def _reach_without(self, blk: Iterable[Tile]) -> set[Tile] | None:
        cut = set(blk)
        reach = set(web_dist(self.passable - cut, self.prot - cut))
        return reach if self.reach - cut <= reach else None

    def _commit(self, obj: PlacedObject, fit: Fit, reach: set[Tile]) -> None:
        allc, blk, approach = fit
        self.lf.covers.add(obj)
        self.objs.append(obj)
        self.occupied.update(allc)
        inflate_gap(self.near, allc)
        self.cells.update(allc)
        self.blk.update(blk)
        self.passable -= set(blk)
        self.reach = reach
        self.approaches.append(approach)
        path = _path_to_web(approach, self.prot, self.passable)
        self.prot.update(path)
        self.reserved.add(approach)
        self.reserved.update(path)

    def _place(self, purpose: str, ident: Identity) -> bool:
        for anchor, fit in self._ranked(purpose, self._fitting(ident)):
            obj = PlacedObject.at(ident, anchor, level=self.lf.level, purpose=purpose)
            if not self.lf.legal(obj) or not self.lf.covers.accepts(obj):
                continue
            reach = self._reach_without(fit[1])
            if reach is None:
                continue
            self._commit(obj, fit, reach)
            return True
        return False

    def _emit_planned(self, obj: PlacedObject) -> bool:
        obj.level = self.lf.level
        if not self.lf.legal(obj) or not self.lf.covers.accepts(obj):
            return False
        self.lf.covers.add(obj)
        self.objs.append(obj)
        return True

    def _write_back(self) -> None:
        zw = self.zw
        zw.gobjs.extend(self.objs)
        zw.occupied = zw.occupied | frozenset(self.cells)
        zw.gblocked = zw.gblocked | frozenset(self.blk)
        zw.approaches = (*zw.approaches, *self.approaches)
        zw.open_set = zw.open_set - self.cells - frozenset(self.approaches)
        zw.passable = zw.passable - self.blk
        zw.prot = frozenset(self.prot)
        zw.planned = []

    def run(self) -> list[PlacedObject]:
        for obj in self.zw.planned:
            if self._emit_planned(obj):
                continue
            ident = Identity(obj.type, obj.subtype, obj.animation, obj.mask)
            if not self._place(obj.purpose, ident):
                print(f"  attractions: no spot for {obj.purpose} {obj.animation}")
        tie_dwellings(self.zw.gobjs)
        self._write_back()
        return self.objs


def place_attractions(zid: int, zw: ZoneWorkspace, lf: LevelField) -> list[PlacedObject]:
    """Emit one zone's planned attractions in draw order. A planned object the cover index
    and terrain rule accept is emitted as is: its footprint and approach are already part
    of ``zw``. A refused one is re-placed and folded into ``zw``: footprints join
    ``occupied``, blocking cells join ``gblocked`` and leave ``passable``, approaches join
    ``approaches`` and link to ``prot`` by a shortest walkable path. The fallback anchor is
    drawn by weighted sampling without replacement over every legal anchor: the corpus
    intensity for the purpose times the count of vegetation cells around the footprint. An
    anchor is legal when its approach is reachable from the web, the footprint keeps every
    reachable tile reachable, and the cover index and terrain rule accept the object."""
    if not zw.planned:
        return []
    return _ZoneAttractions(zid, zw, lf).run()

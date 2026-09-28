"""Subterranean Gate pairs placed against the vegetated field. A pair is one `avtcave` at the
same (x, y) on both levels, inside one zone per level, with its entrance reachable from both
zones' webs. Among the anchors near a spread-admitted tile the one whose sprite tops rest
most against unwalkable tiles, summed over both levels, wins."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import final

from vcmi_mapgen.core.model import PlacedObject, Tile
from vcmi_mapgen.core.steps.gameplay.site import NEIGHBOURHOOD, SiteIndex, ZoneSite, cheb
from vcmi_mapgen.core.steps.gate.gates import (
    GATE_ANIM,
    NO_TILES,
    Fit,
    GateSide,
    Spread,
    gate_anchors,
    rnd_monster,
)
from vcmi_mapgen.vcmi.catalog import objects as ON

GUARD_P = 0.65
GUARD_SALT = 0x6A7F

type Side = tuple[ZoneSite, Fit]


@dataclass
class GateResult:
    """The gate pairs with their guards and the cells they block per level. PortalStep reads
    it with ``ctx.get(GateResult, GateResult())``: a map without subterrain has none."""

    gate_objs: list[PlacedObject] = field(default_factory=list)
    gate_blk: dict[int, frozenset[Tile]] = field(default_factory=dict)


def _side(idx: SiteIndex) -> GateSide:
    return GateSide(frozenset(idx.zone_of), NO_TILES, zone_of=idx.zone_of)


@final
class _GatePlacer:
    def __init__(self, idx0: SiteIndex, idx1: SiteIndex, seed: int) -> None:
        self.idx = (idx0, idx1)
        self.ident = ON.identity_of(GATE_ANIM)
        self.rng = random.Random(seed ^ GUARD_SALT)
        self.cache: dict[tuple[int, Tile], Side | None] = {}
        self.objs: list[PlacedObject] = []
        self.blk: dict[int, set[Tile]] = {0: set(), 1: set()}

    def _fit(self, level: int, t: Tile) -> Side | None:
        key = (level, t)
        if key not in self.cache:
            site = self.idx[level].site_at(t)
            fit = None if site is None else site.fit(self.ident, t)
            self.cache[key] = None if site is None or fit is None else (site, fit)
        return self.cache[key]

    def _back(self, t: Tile, a: Side, b: Side) -> int:
        return a[0].back(self.ident, t) + b[0].back(self.ident, t)

    def place(self, c: Tile, spread: Spread) -> Tile | None:
        cands: list[tuple[int, int, Tile, Side, Side]] = []
        for dx in range(-NEIGHBOURHOOD, NEIGHBOURHOOD + 1):
            for dy in range(-NEIGHBOURHOOD, NEIGHBOURHOOD + 1):
                t = (c[0] + dx, c[1] + dy)
                if not spread.admits(t):
                    continue
                a, b = self._fit(0, t), self._fit(1, t)
                if a is not None and b is not None:
                    cands.append((-self._back(t, a, b), cheb(t, c), t, a, b))
        cands.sort(key=lambda k: (k[0], k[1], k[2]))
        for _back, _d, t, a, b in cands:
            if self._commit(t, a, b):
                return t
        return None

    def _commit(self, t: Tile, a: Side, b: Side) -> bool:
        staged: list[tuple[ZoneSite, Fit, PlacedObject, set[Tile]]] = []
        for level, (site, fit) in enumerate((a, b)):
            obj = PlacedObject.at(self.ident, t, level=level, purpose="TRANSPORT")
            if not site.lf.accepts(obj):
                return False
            reach = site.reach_without(fit[1])
            if reach is None:
                return False
            staged.append((site, fit, obj, reach))
        for site, fit, obj, reach in staged:
            site.commit(obj, fit, reach)
            site.gates += 1
            self.blk[site.lf.level].update(fit[1])
            self.objs.append(obj)
        self.cache.clear()
        if self.rng.random() < GUARD_P and b[0].guard_ok(b[1][2]):
            self.objs.append(b[0].add_guard(rnd_monster(3), b[1][2]))
        return True


def place_gate_pairs(idx0: SiteIndex, idx1: SiteIndex, size: int, seed: int) -> GateResult:
    placer = _GatePlacer(idx0, idx1, seed)
    anchors = gate_anchors(_side(idx0), _side(idx1), size, seed, placer.place)
    print(f"  gates: {len(anchors)} Subterranean Gate pair(s) placed")
    return GateResult(
        gate_objs=placer.objs,
        gate_blk={lvl: frozenset(blk) for lvl, blk in placer.blk.items()},
    )

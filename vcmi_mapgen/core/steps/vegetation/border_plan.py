"""Zone-border plan: every open cross-zone crossing outside the entrance bands is closed with a
blocking decoration while the vegetation step still owns the terrain."""

import collections
import random
from collections.abc import Container, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import final

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import CoverIndex, Identity, PlacedObject, Tile, Zone
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.placement.ground import Ground, stands
from vcmi_mapgen.core.planning.borders import closing_pairs, cross_pairs, zone_owner

MAX_CUT = 4


@dataclass(frozen=True, slots=True)
class BorderPlan:
    land: Iterable[Tile]
    zones: Mapping[int, Zone]
    bands: Container[Tile]
    avoid: Container[Tile]
    web: Container[Tile]
    ground: Ground = ()
    open_pairs: Container[tuple[int, int]] = frozenset[tuple[int, int]]()
    band_ends: Container[tuple[Tile, int]] = frozenset[tuple[Tile, int]]()


@final
class _Sealer:
    def __init__(self, plan: BorderPlan, owner: Mapping[Tile, int], open_all: set[Tile]) -> None:
        self._avoid = plan.avoid
        self._web = plan.web
        self._bands = plan.bands
        self._owner = owner
        self._open_all = open_all
        self.dead: set[Tile] = set()
        self.held: set[Tile] = set()

    def sealable(self, t: Tile) -> bool:
        return (
            t not in self._avoid
            and t not in self.dead
            and t not in self.held
            and t in self._owner
            and t not in self._bands
        )

    def best_pick(self, pairs: list[tuple[Tile, Tile]]) -> Tile | None:
        cnt: collections.Counter[Tile] = collections.Counter()
        for t, n in pairs:
            if self.sealable(t):
                cnt[t] += 1
            if self.sealable(n):
                cnt[n] += 1
        if not cnt:
            return None
        pick, _n = max(cnt.items(), key=lambda kv: (kv[1], kv[0]))
        return pick

    def bridges(self, t: Tile) -> bool:
        """True when the open 4-neighbours of `t` in its own zone stay joined inside that zone
        once `t` is closed."""
        open_all, owner = self._open_all, self._owner
        zid = owner.get(t)
        around = [
            n
            for n in ((t[0] + 1, t[1]), (t[0] - 1, t[1]), (t[0], t[1] + 1), (t[0], t[1] - 1))
            if n in open_all and owner.get(n) == zid
        ]
        if len(around) < 2:
            return True
        want = set(around[1:])
        seen = {around[0]}
        queue = collections.deque([around[0]])
        while queue and want:
            u = queue.popleft()
            for m in ((u[0] + 1, u[1]), (u[0] - 1, u[1]), (u[0], u[1] + 1), (u[0], u[1] - 1)):
                if m == t or m in seen or m not in open_all or owner.get(m) != zid:
                    continue
                seen.add(m)
                want.discard(m)
                queue.append(m)
        return not want

    def cut_off(self, t: Tile) -> frozenset[Tile] | None:
        """The open tiles closing `t` shuts away from the web, or None when they number more
        than `MAX_CUT` or hold a tile to avoid."""
        open_all, web = self._open_all, self._web
        linked: set[Tile] = set()
        cut: set[Tile] = set()
        for nx, ny in ((t[0] + 1, t[1]), (t[0] - 1, t[1]), (t[0], t[1] + 1), (t[0], t[1] - 1)):
            n = (nx, ny)
            if n not in open_all or n in linked or n in cut:
                continue
            seen = {n}
            queue = collections.deque([n])
            found = n in web
            while queue and not found:
                u = queue.popleft()
                for m in ((u[0] + 1, u[1]), (u[0] - 1, u[1]), (u[0], u[1] + 1), (u[0], u[1] - 1)):
                    if m == t or m in seen or m not in open_all:
                        continue
                    if m in web or m in linked:
                        found = True
                        break
                    seen.add(m)
                    queue.append(m)
            if found:
                linked |= seen
            else:
                cut |= seen
        if len(cut) > MAX_CUT or any(c in self._avoid or c not in self._owner for c in cut):
            return None
        return frozenset(cut)


def _pool(catalog: Catalog, terrain: str, cell: Tile, ground: Ground) -> list[Identity]:
    return [
        i
        for i in catalog.decor(terrain, blocking=True, max_cells=1)
        if stands(catalog, i, cell, ground)
    ]


def _decor_for(
    catalog: Catalog,
    cells: Sequence[Tile],
    tname: Mapping[Tile, str],
    ground: Ground,
    rng: random.Random,
) -> list[Identity] | None:
    """One decoration for each of ``cells``, drawn for its zone's terrain, or for the tile's
    own terrain when none of those stands there. None when a cell takes none."""
    out: list[Identity] = []
    for cell in cells:
        pool = _pool(catalog, tname[cell], cell, ground)
        if not pool and ground:
            pool = _pool(catalog, catalog.terrain_name(ground[cell[1]][cell[0]]), cell, ground)
        if not pool:
            return None
        out.append(rng.choice(pool))
    return out


def seal_borders(
    catalog: Catalog,
    plan: BorderPlan,
    objs: list[PlacedObject],
    seed: int,
    level: int,
) -> tuple[list[PlacedObject], set[Tile]]:
    """Close cross-zone crossings with single corpus-weighted 1x1 blocking decorations.

    The border bias densifies zone fronts statistically, but jagged fronts leave aligned
    open pairs a hero can walk or diagonal-step through. This pass picks, greedily, the tile
    that kills the most remaining pairs. `avoid` holds tiles that must stay open (protected
    web, approaches, tunnels). A pair whose both sides are in `avoid` stays open and is left
    to the guard pass. A cell is only sealed when every open 4-neighbour still reaches the
    web, or when the few tiles it would shut away are sealed with it. A cell that fails that
    test is tried again once another cell is sealed. A decoration only seals a cell whose
    terrain it may stand on. A crossing between an `open_pairs` zone pair stays open.
    Returns (new_objs, sealed_cells)."""
    rng = random.Random(seed ^ 0x5EA1 ^ (level * 7919))
    owner, tname = zone_owner(catalog, plan.zones)
    blocked = FP.blocking_cells(objs)
    open_all = set(plan.land) - blocked
    crossing = cross_pairs(open_all, owner, plan.band_ends)[0]
    pairs: list[tuple[Tile, Tile]] = closing_pairs(crossing, owner, plan.open_pairs)
    sealer = _Sealer(plan, owner, open_all)

    new_objs: list[PlacedObject] = []
    cover = CoverIndex(objs)
    sealed: set[Tile] = set()
    moved = False
    while pairs:
        pick = sealer.best_pick(pairs)
        if pick is None and moved:
            sealer.held.clear()
            moved = False
            continue
        if pick is None:
            break
        cut = frozenset[Tile]() if pick in plan.web else sealer.cut_off(pick)
        if cut is None or (pick in plan.web and not sealer.bridges(pick)):
            sealer.held.add(pick)
            continue
        cells = [pick, *sorted(cut)]
        idents = _decor_for(catalog, cells, tname, plan.ground, rng) or []
        decor = [
            PlacedObject.at(i, c, level=level, purpose="")
            for i, c in zip(idents, cells, strict=False)
        ]
        mark = cover.mark()
        if not idents or not all(cover.try_add(d) for d in decor):
            cover.rollback(mark)
            (sealer.dead if not cut else sealer.held).add(pick)
            continue
        new_objs += decor
        sealed.update(cells)
        moved = True
        open_all.difference_update(cells)
        pairs = [p for p in pairs if not set(p) & set(cells)]
    return new_objs, sealed

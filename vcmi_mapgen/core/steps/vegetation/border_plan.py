"""Zone-border plan: every open cross-zone crossing outside the entrance bands is closed with a
blocking decoration while the vegetation step still owns the terrain."""

import collections
import random
from collections.abc import Container, Iterable, Mapping
from dataclasses import dataclass
from typing import final

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import CoverIndex, PlacedObject, Tile, Zone
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.planning.borders import cross_pairs, zone_owner


@dataclass(frozen=True, slots=True)
class BorderPlan:
    land: Iterable[Tile]
    zones: Mapping[int, Zone]
    bands: Container[Tile]
    avoid: Container[Tile]
    web: Container[Tile]


@final
class _Sealer:
    def __init__(self, plan: BorderPlan, owner: Mapping[Tile, int], open_all: set[Tile]) -> None:
        self._avoid = plan.avoid
        self._web = plan.web
        self._bands = plan.bands
        self._owner = owner
        self._open_all = open_all
        self.dead: set[Tile] = set()

    def sealable(self, t: Tile) -> bool:
        return (
            t not in self._avoid
            and t not in self.dead
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
        """True when the open 4-neighbours of `t` stay joined once `t` is closed."""
        open_all = self._open_all
        around = [
            n
            for n in ((t[0] + 1, t[1]), (t[0] - 1, t[1]), (t[0], t[1] + 1), (t[0], t[1] - 1))
            if n in open_all
        ]
        if len(around) < 2:
            return True
        want = set(around[1:])
        seen = {around[0]}
        queue = collections.deque([around[0]])
        while queue and want:
            u = queue.popleft()
            if len(seen) > 400:
                return True
            for m in ((u[0] + 1, u[1]), (u[0] - 1, u[1]), (u[0], u[1] + 1), (u[0], u[1] - 1)):
                if m == t or m in seen or m not in open_all:
                    continue
                seen.add(m)
                want.discard(m)
                queue.append(m)
        return not want

    def keeps_connected(self, t: Tile) -> bool:
        open_all, avoid, web = self._open_all, self._avoid, self._web
        linked: set[Tile] = set()
        for nx, ny in ((t[0] + 1, t[1]), (t[0] - 1, t[1]), (t[0], t[1] + 1), (t[0], t[1] - 1)):
            n = (nx, ny)
            if n not in open_all or n in linked:
                continue
            seen = {n}
            queue = collections.deque([n])
            found = n in avoid or n in web
            while queue and not found:
                u = queue.popleft()
                for m in ((u[0] + 1, u[1]), (u[0] - 1, u[1]), (u[0], u[1] + 1), (u[0], u[1] - 1)):
                    if m == t or m in seen or m not in open_all:
                        continue
                    if m in avoid or m in web or m in linked:
                        found = True
                        break
                    seen.add(m)
                    queue.append(m)
            if not found:
                return False
            linked |= seen
        return True


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
    to the guard pass. A cell is only sealed when every open 4-neighbour still reaches an
    `avoid` tile. Returns (new_objs, sealed_cells)."""
    rng = random.Random(seed ^ 0x5EA1 ^ (level * 7919))
    owner, tname = zone_owner(catalog, plan.zones)
    blocked = FP.blocking_cells(objs)
    open_all = set(plan.land) - blocked
    pairs: list[tuple[Tile, Tile]] = cross_pairs(open_all, owner, plan.bands)[0]
    sealer = _Sealer(plan, owner, open_all)

    new_objs: list[PlacedObject] = []
    cover = CoverIndex(objs)
    sealed: set[Tile] = set()
    while pairs:
        pick = sealer.best_pick(pairs)
        if pick is None:
            break
        pool = catalog.decor(tname[pick], blocking=True, max_cells=1)
        joined = sealer.bridges(pick) if pick in plan.web else sealer.keeps_connected(pick)
        if not pool or not joined:
            sealer.dead.add(pick)
            continue
        decor = PlacedObject.at(rng.choice(pool), pick, level=level, purpose="")
        if not cover.try_add(decor):
            sealer.dead.add(pick)
            continue
        new_objs.append(decor)
        sealed.add(pick)
        open_all.discard(pick)
        pairs = [p for p in pairs if pick not in p]
    return new_objs, sealed

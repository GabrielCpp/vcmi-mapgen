"""Zone-border plan: every open cross-zone crossing outside the entrance bands is closed with a
blocking decoration while the vegetation step still owns the terrain."""

import collections
import random
from collections.abc import Collection, Container, Iterable, Mapping
from dataclasses import dataclass
from typing import final

from vcmi_mapgen import ontology as ON
from vcmi_mapgen.core.model import CoverIndex, PlacedObject, Tile, Zone
from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.kit.terrain_lookup import EXCLUDE_DECOR_TYPES, TNAME


def blocking_cells(o: PlacedObject) -> list[Tile]:
    return [(cx, cy) for cx, cy, blk in OR.mask_cells(o.mask, o.x, o.y) if blk]


def zone_owner(zones: Mapping[int, Zone]) -> tuple[dict[Tile, int], dict[Tile, str]]:
    """Land tile to zone id and terrain name, water and rock zones left out."""
    owner: dict[Tile, int] = {}
    tname: dict[Tile, str] = {}
    for zid, z in sorted(zones.items()):
        terr = TNAME.get(z.terrain_type)
        if terr is None or terr in ("water", "rock"):
            continue
        for t in z.tiles_set:
            owner[t] = zid
            tname[t] = terr
    return owner, tname


def cross_pairs(
    open_all: Collection[Tile],
    owner: Mapping[Tile, int],
    bands: Container[Tile],
    skip_tiles: Container[Tile] = (),
) -> tuple[list[tuple[Tile, Tile]], list[tuple[Tile, Tile]]]:
    """8-adjacent open pairs across a zone border, each unordered pair once.

    Returns (plain pairs, pairs touching an entrance band)."""
    pairs: list[tuple[Tile, Tile]] = []
    band_pairs: list[tuple[Tile, Tile]] = []
    for t in sorted(open_all):
        a = owner.get(t)
        if a is None or t in skip_tiles:
            continue
        for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
            n = (t[0] + dx, t[1] + dy)
            if n not in open_all or n in skip_tiles:
                continue
            b = owner.get(n)
            if b is not None and b != a:
                if t in bands or n in bands:
                    band_pairs.append((t, n))
                else:
                    pairs.append((t, n))
    return pairs, band_pairs


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
    owner, tname = zone_owner(plan.zones)
    blocked: set[Tile] = set()
    for o in objs:
        blocked.update(blocking_cells(o))
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
        pool = ON.decor_pool(
            tname[pick], blocking=True, max_cells=1, exclude_types=EXCLUDE_DECOR_TYPES
        )
        joined = sealer.bridges(pick) if pick in plan.web else sealer.keeps_connected(pick)
        if not pool or not joined:
            sealer.dead.add(pick)
            continue
        decor = PlacedObject.at(rng.choice(pool), pick, level=0, purpose="")
        if not cover.try_add(decor):
            sealer.dead.add(pick)
            continue
        new_objs.append(decor)
        sealed.add(pick)
        open_all.discard(pick)
        pairs = [p for p in pairs if pick not in p]
    return new_objs, sealed

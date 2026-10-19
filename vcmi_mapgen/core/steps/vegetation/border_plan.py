"""Zone-border plan: every open cross-zone crossing outside the entrance bands is closed with a
blocking decoration while the vegetation step still owns the terrain, and the wall between
two territories is thickened to its planned width."""

import collections
import heapq
import random
from collections.abc import Container, Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from typing import final

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.reach import STEPS4, STEPS8
from vcmi_mapgen.core.model import CoverIndex, Identity, PlacedObject, Tile, Zone
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.placement.ground import Ground, stands
from vcmi_mapgen.core.planning.borders import closing_pairs, cross_pairs, deep_pairs, zone_owner

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
    depths: Mapping[tuple[int, int], int] = field(default_factory=dict[tuple[int, int], int])


@final
class _Sealer:
    def __init__(self, plan: BorderPlan, owner: Mapping[Tile, int], open_all: set[Tile]) -> None:
        self._avoid = plan.avoid
        self._web = plan.web
        self._bands = plan.bands
        self._owner = owner
        self._open_all = open_all
        self._walls = _Walls(open_all)
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

    def close(self, cells: Iterable[Tile]) -> None:
        for c in cells:
            self._open_all.discard(c)
            self._walls.add(c)

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
        than `MAX_CUT`, hold a tile to avoid, or hold a piece of the web. Two pieces too big to
        cut away rule `t` out at once when they stay apart."""
        open_all = self._open_all
        big = [n for n in _around(t) if n in open_all and not _small(open_all, t, n)]
        if any(not self._walls.joined(t, big[0], n) for n in big[1:]):
            return None
        live, closed = _split(open_all, t, frozenset(big))
        held_web = [g for g in closed if any(c in self._web for c in g)]
        if len(held_web) > (0 if live else 1):
            return None
        cut = {c for g in closed if g not in held_web for c in g}
        if len(cut) > MAX_CUT or any(c in self._avoid or c not in self._owner for c in cut):
            return None
        return frozenset(cut)


@final
class _Pairs:
    """The pairs still open and, for each tile a seal may take, how many of them it
    touches. The best tile touches the most, the highest tile first on a tie."""

    def __init__(self, pairs: Sequence[tuple[Tile, Tile]], sealer: _Sealer) -> None:
        self._pairs = pairs
        self._alive = [True] * len(pairs)
        self.left = len(pairs)
        self._of: dict[Tile, list[int]] = collections.defaultdict(list)
        for i, (t, n) in enumerate(pairs):
            self._of[t].append(i)
            self._of[n].append(i)
        self._count = {t: len(ids) for t, ids in self._of.items()}
        self._sealer = sealer
        self._heap: list[tuple[int, int, int]] = []
        self.push(self._count)

    def push(self, tiles: Iterable[Tile]) -> None:
        for t in tiles:
            if self._count.get(t, 0) and self._sealer.sealable(t):
                heapq.heappush(self._heap, (-self._count[t], -t[0], -t[1]))

    def best(self) -> Tile | None:
        while self._heap:
            n, x, y = self._heap[0]
            t = (-x, -y)
            if -n == self._count[t] and self._sealer.sealable(t):
                return t
            _ = heapq.heappop(self._heap)
        return None

    def close(self, cells: Iterable[Tile]) -> None:
        for c in cells:
            for i in self._of.get(c, ()):
                if not self._alive[i]:
                    continue
                self._alive[i] = False
                self.left -= 1
                for end in self._pairs[i]:
                    self._count[end] -= 1
                self.push(self._pairs[i])


_RING = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))


@final
class _Walls:
    """The tiles shut to a hero, joined 8-way, with everything past the open land one wall.
    Two open 4-neighbours of a tile fall apart once it closes exactly when a wall on one side
    of it, between them, is joined to a wall on the other side."""

    def __init__(self, open_all: AbstractSet[Tile]) -> None:
        self._open = open_all
        xs = [x for x, _ in open_all] or [0]
        ys = [y for _, y in open_all] or [0]
        self._box = (min(xs), min(ys), max(xs), max(ys))
        self._outside = (min(xs) - 1, min(ys) - 1)
        self._root: dict[Tile, Tile] = {self._outside: self._outside}
        shut = [
            (x, y)
            for x in range(min(xs), max(xs) + 1)
            for y in range(min(ys), max(ys) + 1)
            if (x, y) not in open_all
        ]
        self._root.update((t, t) for t in shut)
        for t in shut:
            self._join(t)

    def _find(self, t: Tile) -> Tile:
        x0, y0, x1, y1 = self._box
        if not (x0 <= t[0] <= x1 and y0 <= t[1] <= y1):
            t = self._outside
        root = self._root
        while root[t] != t:
            root[t] = root[root[t]]
            t = root[t]
        return t

    def _join(self, t: Tile) -> None:
        for dx, dy in STEPS8:
            n = (t[0] + dx, t[1] + dy)
            if n not in self._open and (b := self._find(n)) != (a := self._find(t)):
                self._root[b] = a

    def add(self, t: Tile) -> None:
        self._root[t] = t
        self._join(t)

    def joined(self, t: Tile, a: Tile, b: Tile) -> bool:
        """True when the open 4-neighbours `a` and `b` of `t` stay joined once `t` closes."""
        ring = [(t[0] + dx, t[1] + dy) for dx, dy in _RING]
        i, j = sorted((ring.index(a), ring.index(b)))
        one = {self._find(c) for c in ring[i + 1 : j] if c not in self._open}
        two = {self._find(c) for c in ring[j + 1 :] + ring[:i] if c not in self._open}
        return not one & two


def _around(t: Tile) -> tuple[Tile, ...]:
    return tuple((t[0] + dx, t[1] + dy) for dx, dy in STEPS4)


@final
class _Flood:
    """The pieces the open 4-neighbours of a closed tile fall into. Each piece floods in step
    with the others, and a piece that runs dry is whole."""

    def __init__(self, open_all: AbstractSet[Tile], t: Tile) -> None:
        self._open = open_all
        self._t = t
        starts = [n for n in _around(t) if n in open_all]
        self.starts = starts
        self.label = {n: i for i, n in enumerate(starts)}
        self.root = list(range(len(starts)))
        self.queues = {i: collections.deque([n]) for i, n in enumerate(starts)}
        self.closed: list[int] = []

    def find(self, i: int) -> int:
        while self.root[i] != i:
            i = self.root[i]
        return i

    def grow(self, i: int) -> None:
        queue = self.queues[i]
        if not queue:
            self.closed.append(i)
            del self.queues[i]
            return
        for m in _around(queue.popleft()):
            if m == self._t or m not in self._open:
                continue
            j = self.label.get(m)
            if j is None:
                self.label[m] = i
                queue.append(m)
            elif (b := self.find(j)) != i:
                self.root[b] = i
                queue.extend(self.queues.pop(b))


def _small(open_all: AbstractSet[Tile], t: Tile, start: Tile) -> bool:
    """True when the open piece `start` falls into once `t` closes holds at most `MAX_CUT`
    tiles."""
    seen = {start}
    stack = [start]
    while stack:
        for m in _around(stack.pop()):
            if m != t and m in open_all and m not in seen:
                if len(seen) == MAX_CUT:
                    return False
                seen.add(m)
                stack.append(m)
    return True


def _split(
    open_all: AbstractSet[Tile], t: Tile, big: AbstractSet[Tile]
) -> tuple[bool, list[set[Tile]]]:
    """The pieces the open 4-neighbours of `t` fall into once `t` closes. The flood stops
    once a single piece still grows, or once only pieces grown from `big` grow, which the
    caller knows to be one. Returns whether that piece remains, and the whole pieces."""
    flood = _Flood(open_all, t)
    while len(flood.queues) > 1 and not all(flood.starts[i] in big for i in flood.queues):
        for i in list(flood.queues):
            if i in flood.queues:
                flood.grow(i)
    pieces = [{m for m, j in flood.label.items() if flood.find(j) == c} for c in flood.closed]
    return bool(flood.queues), pieces


@final
class _Decor:
    """The blocking decorations a seal draws from, one pool per terrain."""

    def __init__(self, catalog: Catalog, tname: Mapping[Tile, str], ground: Ground) -> None:
        self._catalog = catalog
        self._tname = tname
        self._ground = ground
        self._kinds: dict[str, list[Identity]] = {}
        self._larger: dict[str, list[tuple[Identity, tuple[Tile, ...]]]] = {}

    def _pool(self, terrain: str, cell: Tile) -> list[Identity]:
        if terrain not in self._kinds:
            self._kinds[terrain] = self._catalog.decor(terrain, blocking=True, max_cells=1)
        return [i for i in self._kinds[terrain] if stands(self._catalog, i, cell, self._ground)]

    def _terrains(self, cell: Tile) -> list[str]:
        out = [self._tname[cell]]
        if self._ground:
            out.append(self._catalog.terrain_name(self._ground[cell[1]][cell[0]]))
        return out

    def _single(self, cell: Tile) -> list[Identity]:
        pool = self._pool(self._tname[cell], cell)
        if not pool and self._ground:
            ground = self._ground[cell[1]][cell[0]]
            pool = self._pool(self._catalog.terrain_name(ground), cell)
        return pool

    def _multi(self, terrain: str) -> list[tuple[Identity, tuple[Tile, ...]]]:
        if terrain not in self._larger:
            found: list[tuple[Identity, tuple[Tile, ...]]] = []
            for ident in self._catalog.decor(terrain, blocking=True):
                blk = FP.cell_offsets(ident.footprint)[1]
                if len(blk) >= 2:
                    found.append((ident, blk))
            self._larger[terrain] = found
        return self._larger[terrain]

    def _fits(
        self, cell: Tile, cells: AbstractSet[Tile], shut: Container[Tile]
    ) -> list[tuple[Identity, Tile, tuple[Tile, ...]]]:
        fits: list[tuple[Identity, Tile, tuple[Tile, ...]]] = []
        for terrain in self._terrains(cell):
            for ident, blk in self._multi(terrain):
                for ox, oy in blk:
                    anchor = (cell[0] - ox, cell[1] - oy)
                    covered = tuple((anchor[0] + dx, anchor[1] + dy) for dx, dy in blk)
                    if all(c in cells or c in shut for c in covered) and stands(
                        self._catalog, ident, anchor, self._ground
                    ):
                        fits.append((ident, anchor, covered))
            if fits:
                break
        return sorted(fits, key=lambda f: (f[0].type or "", f[0].subtype or "", f[1]))

    def draw(self, cells: Sequence[Tile], rng: random.Random) -> list[tuple[Identity, Tile]] | None:
        """One 1x1 decoration for each of ``cells``, drawn for its zone's terrain, or for the
        tile's own terrain when none of those stands there. None when a cell takes none."""
        out: list[tuple[Identity, Tile]] = []
        for cell in cells:
            pool = self._single(cell)
            if not pool:
                return None
            out.append((rng.choice(pool), cell))
        return out

    def draw_pieces(
        self, cells: Sequence[Tile], shut: Container[Tile], rng: random.Random
    ) -> list[tuple[Identity, Tile]] | None:
        """The pieces that close ``cells``. A cell takes a piece of two or more blocking cells
        when the rest of its blocking cells fall on other ``cells`` or on tiles in ``shut``,
        and a 1x1 decoration otherwise. None when a cell takes none."""
        members = frozenset(cells)
        done: set[Tile] = set()
        out: list[tuple[Identity, Tile]] = []
        for cell in cells:
            if cell in done:
                continue
            pool = self._single(cell)
            if not pool:
                return None
            if fits := self._fits(cell, members, shut):
                ident, anchor, covered = rng.choice(fits)
                out.append((ident, anchor))
                done.update(covered)
            else:
                out.append((rng.choice(pool), cell))
                done.add(cell)
        return out


def seal_borders(
    catalog: Catalog,
    plan: BorderPlan,
    objs: list[PlacedObject],
    seed: int,
    level: int,
) -> tuple[list[PlacedObject], set[Tile]]:
    """Close cross-zone crossings with single corpus-weighted 1x1 blocking decorations, and
    every pair of open tiles of two zones no farther apart than the wall width ``depths``
    gives them.

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
    sealer = _Sealer(plan, owner, open_all)
    pairs = _Pairs(
        closing_pairs(crossing, owner, plan.open_pairs) + deep_pairs(open_all, owner, plan.depths),
        sealer,
    )

    new_objs: list[PlacedObject] = []
    decor_of = _Decor(catalog, tname, plan.ground)
    cover = CoverIndex(objs)
    sealed: set[Tile] = set()
    moved = False
    while pairs.left:
        pick = pairs.best()
        if pick is None and moved:
            held = sorted(sealer.held)
            sealer.held.clear()
            pairs.push(held)
            moved = False
            continue
        if pick is None:
            break
        cut = sealer.cut_off(pick)
        if cut is None or (pick in plan.web and (cut or not sealer.bridges(pick))):
            sealer.held.add(pick)
            continue
        cells = [pick, *sorted(cut)]
        shut = blocked | sealed
        mark = cover.mark()
        decor: list[PlacedObject] = []
        pieces = decor_of.draw_pieces(cells, shut, rng)
        tries = [pieces]
        if pieces and any(len(FP.cell_offsets(i.footprint)[1]) > 1 for i, _a in pieces):
            tries.append(decor_of.draw(cells, rng))
        for drawn in tries:
            decor = [PlacedObject.at(i, a, level=level, purpose="") for i, a in (drawn or [])]
            if drawn and all(cover.try_add(d) for d in decor):
                break
            cover.rollback(mark)
            decor = []
        if not decor:
            (sealer.dead if not cut else sealer.held).add(pick)
            continue
        new_objs += decor
        sealed.update(cells)
        moved = True
        sealer.close(cells)
        pairs.close(cells)
    return new_objs, sealed

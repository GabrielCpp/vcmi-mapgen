"""Border guards: a hostile guard on every cross-zone crossing left open after the plan."""

import random
from collections.abc import Collection, Container, Mapping, Sequence
from dataclasses import dataclass
from typing import final

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import CoverIndex, PlacedObject, Tile, Zone
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.placement.guards import guard_spaced
from vcmi_mapgen.core.planning.borders import cross_pairs, zone_owner


@dataclass(frozen=True, slots=True)
class LevelGrid:
    width: int
    height: int
    grid: Sequence[Sequence[int]]
    zones: Mapping[int, Zone]
    level: int = 0


@dataclass(frozen=True, slots=True)
class CrossingRules:
    bands: Container[Tile]
    hard_avoid: Container[Tile]
    skip_tiles: Container[Tile] = ()


@final
class _GuardPlacer:
    def __init__(
        self,
        catalog: Catalog,
        rng: random.Random,
        objs: list[PlacedObject],
        hard_avoid: Container[Tile],
        decor_blk: Container[Tile],
    ) -> None:
        self._catalog = catalog
        self._rng = rng
        self._hard_avoid = hard_avoid
        self._cover = CoverIndex(objs)
        self._decor_blk = decor_blk
        self._guards = [(o.x, o.y) for o in objs if o.purpose == Purpose.GUARD]

    @staticmethod
    def _covered(t: Tile, n: Tile, g_set: Collection[Tile]) -> bool:
        return any(
            max(abs(g[0] - t[0]), abs(g[1] - t[1])) <= 1
            or max(abs(g[0] - n[0]), abs(g[1] - n[1])) <= 1
            for g in g_set
        )

    def _pick_guard(self, cands: Sequence[Tile]) -> Tile:
        """First candidate whose sprite overlay is clear of decor; else the first."""
        rnd = self._catalog.guard(3)
        for c in cands:
            if FP.overlay_clear(rnd.footprint, c[0], c[1], self._decor_blk):
                return c
        return cands[0]

    def _stand_guard(self, cands: Sequence[Tile]) -> PlacedObject | None:
        first = self._pick_guard(cands)
        for g in [first, *(c for c in cands if c != first)]:
            if not guard_spaced(g, self._guards):
                continue
            gident = self._catalog.guard(3 + (1 if self._rng.random() < 0.3 else 0))
            guard = PlacedObject.at(
                gident, g, level=0, purpose=Purpose.GUARD, options={"character": "hostile"}
            )
            if self._cover.try_add(guard):
                self._guards.append(g)
                return guard
        return None

    def guard_pairs(
        self,
        pairs: Sequence[tuple[Tile, Tile]],
        fixed: set[Tile],
        new_objs: list[PlacedObject],
    ) -> tuple[set[Tile], int]:
        placed: set[Tile] = set()
        unguarded = 0
        for t, n in pairs:
            if self._covered(t, n, fixed | placed):
                continue
            cands = [c for c in sorted((t, n)) if c not in self._hard_avoid]
            if not cands:
                unguarded += 1
                continue
            guard = self._stand_guard(cands)
            if guard is None:
                unguarded += 1
                continue
            guard.seal = True
            new_objs.append(guard)
            placed.add((guard.x, guard.y))
        return placed, unguarded


def guard_crossings(
    catalog: Catalog,
    terrain: LevelGrid,
    rules: CrossingRules,
    objs: list[PlacedObject],
    seed: int,
) -> tuple[list[PlacedObject], set[Tile], int]:
    """Guard every cross-zone crossing that stays open after the vegetation border plan.

    A crossing outside the entrance bands is a back path the plan could not close. A crossing
    inside a band is a planned entrance and must cost a fight. One guard's zone of control
    covers every crossing within Chebyshev 1, so a run of adjacent crossings shares one guard.
    Guards never stand on `hard_avoid` tiles (gameplay cells, approaches, pickups), nor
    within Chebyshev 2 of another guard.
    Returns (new_objs, guard_tiles, n_unguarded_pairs)."""
    rng = random.Random(seed ^ 0x6A4D ^ (terrain.level * 7919))
    owner, _tname = zone_owner(catalog, terrain.zones)
    blocked = FP.blocking_cells(objs)
    grid = terrain.grid
    open_all = {
        (x, y) for y in range(terrain.height) for x in range(terrain.width) if grid[y][x] < 8
    } - blocked
    pairs, band_pairs = cross_pairs(open_all, owner, rules.bands, rules.skip_tiles)
    new_objs: list[PlacedObject] = []

    existing_guards = {(o.x, o.y) for o in objs if o.purpose == Purpose.GUARD}

    decor_blk = FP.decor_blocking_cells(objs + new_objs)
    placer = _GuardPlacer(catalog, rng, objs, rules.hard_avoid, decor_blk)

    guard_tiles, unguarded = placer.guard_pairs(pairs, existing_guards, new_objs)

    band_guard_tiles, _ = placer.guard_pairs(band_pairs, guard_tiles | existing_guards, new_objs)

    guard_tiles |= band_guard_tiles
    return new_objs, guard_tiles, unguarded

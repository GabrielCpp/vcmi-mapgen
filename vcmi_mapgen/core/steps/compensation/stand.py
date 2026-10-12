"""Where a prize stands: an artifact on a tile its player reaches first, with its guard on a
tile beside it, the guard's zone covering no other object's entrance and adding less
than a day to any hero's way."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import cast

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.distance import object_distance
from vcmi_mapgen.core.model import Identity, MapState, PlacedObject, Tile
from vcmi_mapgen.core.model.map_state import CoverIndex
from vcmi_mapgen.core.model.payload import Guard
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.placement.ground import stands
from vcmi_mapgen.core.placement.guards import guard_spaced, zoc_of
from vcmi_mapgen.core.reading.effort import EffortMap
from vcmi_mapgen.core.reading.routes import RouteMap, Spot

DETOUR = 1.0
NEIGHBOURS: tuple[Tile, ...] = tuple(
    (dx, dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dx, dy) != (0, 0)
)


class PrizeStand:
    """The objects of every level as the prizes land among them, and the unguarded open tiles
    the prizes leave a hero."""

    def __init__(self, catalog: Catalog, state: MapState, route: RouteMap) -> None:
        self.catalog: Catalog = catalog
        self.state: MapState = state
        self.route: RouteMap = route
        by_level = state.objs_by_level(route.levels())
        self.covers: dict[int, CoverIndex] = {lv: CoverIndex(objs) for lv, objs in by_level.items()}
        self.guards: dict[int, list[Tile]] = {
            lv: [(o.x, o.y) for o in objs if o.purpose == Purpose.GUARD]
            for lv, objs in by_level.items()
        }
        self.distance: dict[int, list[list[int]]] = {
            lv: cast(list[list[int]], object_distance(state.size, _gameplay_cells(objs)).tolist())
            for lv, objs in by_level.items()
        }
        self.closed: dict[Spot, int] = {}
        self.placed: list[tuple[PlacedObject, PlacedObject]] = []

    def ground(self) -> list[Spot]:
        """Every open, free land tile, in tile order."""
        return [
            Spot(lv, x, y)
            for lv in self.route.levels()
            for y in range(self.state.size)
            for x in range(self.state.size)
            if self._bare(lv, (x, y))
        ]

    def order(self, spots: Sequence[Spot]) -> list[Spot]:
        """``spots`` furthest from any gameplay object first, ties in tile order."""
        return sorted(spots, key=lambda s: (-self.distance[s.level][s.y][s.x], s.level, s.y, s.x))

    def place(
        self,
        spot: Spot,
        art: Identity,
        guard: tuple[Identity, int],
        maps: Sequence[EffortMap],
    ) -> tuple[PlacedObject, PlacedObject] | None:
        """The artifact on ``spot`` and its guard, an identity and its level, on the first tile
        beside it that fits, None when no tile does. A guard fits only where it adds less than
        ``DETOUR`` days to the way of each player of ``maps`` to any tile."""
        level, tile = spot.level, (spot.x, spot.y)
        ground = self.state.terrain.get(level, ())
        cover = self.covers[level]
        prize = PlacedObject.at(art, tile, level=level, purpose=Purpose.REWARD_PICKUP)
        if not (stands(self.catalog, art, tile, ground) and cover.accepts(prize)):
            return None
        ident, strength = guard
        for g in self._beside(tile):
            keeper = PlacedObject.at(ident, g, level=level, purpose=Purpose.GUARD, payload=Guard())
            zone = zoc_of(g)
            held = {Spot(level, *t): strength for t in zone | {tile} if self.state.in_bounds(*t)}
            if not (
                self._bare(level, g)
                and not any(self._entered(level, t) for t in zone - {tile})
                and stands(self.catalog, ident, g, ground)
                and guard_spaced(g, self.guards[level])
                and cover.accepts(keeper)
                and all(em.detour({**self.closed, **held}) < DETOUR for em in maps)
            ):
                continue
            cover.add(prize)
            cover.add(keeper)
            self.guards[level].append(g)
            self.closed |= held
            self.placed.append((prize, keeper))
            return prize, keeper
        return None

    def _beside(self, tile: Tile) -> Iterator[Tile]:
        for dx, dy in NEIGHBOURS:
            g = (tile[0] + dx, tile[1] + dy)
            if self.state.in_bounds(*g):
                yield g

    def _passable(self, level: int, t: Tile) -> bool:
        x, y = t
        return (
            self.state.in_bounds(x, y)
            and self.route.open[level][y][x]
            and not self.route.guard[level][y][x]
            and Spot(level, x, y) not in self.closed
        )

    def _entered(self, level: int, t: Tile) -> bool:
        x, y = t
        view = self.state.at(level, x, y)
        return view.visitable or view.approach or Spot(level, x, y) in self.closed

    def _bare(self, level: int, t: Tile) -> bool:
        x, y = t
        return (
            self._passable(level, t)
            and not self.route.water[level][y][x]
            and self.state.at(level, x, y).free
        )


def _gameplay_cells(objs: Sequence[PlacedObject]) -> list[Tile]:
    return [
        t
        for o in objs
        if o.purpose != Purpose.GUARD and o.footprint.cells
        for t in FP.interactive_cells(o.footprint, o.x, o.y)
    ]

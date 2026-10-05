"""Whether every player reaches a mine of each basic resource: per player and resource, the
hero-days to the nearest such mine, and per resource the gap between the players.

A hero visits a mine by stepping on its entrance from a tile beside it, so a mine's effort
includes the toll of the guard covering the entrance."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState, PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.reading.effort import EffortMap, effort_map
from vcmi_mapgen.core.reading.homes import town_homes
from vcmi_mapgen.core.reading.routes import Spot, route_map

PROMISE_DAYS = 14
PROMISE_GAP = 3


def mine_resource(catalog: Catalog, obj: PlacedObject) -> str | None:
    """The resource a mine yields, None for any other object."""
    if obj.purpose != Purpose.MINE:
        return None
    subtype = catalog.identity_of(obj.kind).subtype
    return None if subtype is None else str(subtype)


def doors(obj: PlacedObject) -> list[Spot]:
    """The entrance tiles of ``obj``."""
    cells = [t for t, role in obj.footprint.at(obj.x, obj.y) if role.interactive]
    return [Spot(obj.level, x, y) for x, y in cells or [(obj.x, obj.y)]]


def effort_to(em: EffortMap, objs: Iterable[PlacedObject]) -> int | None:
    """The cheapest effort in days to visit any of ``objs``, None when none is reached."""
    found = [e.total for o in objs for d in doors(o) if (e := em.visit(d)) is not None]
    return min(found) if found else None


@dataclass(frozen=True, slots=True)
class Promise:
    """Per player, in the order of ``player_towns``, the days to the nearest mine of each
    resource, None when no such mine is reached."""

    days: tuple[Mapping[str, int | None], ...]

    def gap(self, res: str) -> int | None:
        """The days between the nearest and the farthest player, None when one is not
        reached."""
        found = [d[res] for d in self.days]
        if not found or any(v is None for v in found):
            return None
        reached = [v for v in found if v is not None]
        return max(reached) - min(reached)

    def broken(self, limit: int = PROMISE_DAYS, gap: int = PROMISE_GAP) -> list[str]:
        """Each breach as one line: a player past ``limit`` days of a resource, or a resource
        whose gap passes ``gap``."""
        out: list[str] = []
        resources = sorted({r for d in self.days for r in d})
        for i, d in enumerate(self.days):
            out.extend(
                f"player {i} {r}: {d[r]} days"
                for r in resources
                if d.get(r) is None or (v := d[r]) is None or v > limit
            )
        for r in resources:
            g = self.gap(r)
            if g is not None and g > gap:
                out.append(f"{r}: gap {g} days")
        return out


def player_maps(catalog: Catalog, map_state: MapState, toll: Sequence[int]) -> list[EffortMap]:
    """One effort map per player, in the order of ``player_towns``, each from its own town."""
    route = route_map(catalog, map_state)
    return [effort_map(route, spots, toll) for spots in town_homes(map_state)]


def _mines(
    catalog: Catalog, objs: Iterable[PlacedObject], resources: Sequence[str]
) -> dict[str, list[PlacedObject]]:
    mines: dict[str, list[PlacedObject]] = {r: [] for r in resources}
    for o in objs:
        res = mine_resource(catalog, o)
        if res in mines:
            mines[res].append(o)
    return mines


def promise_from(
    catalog: Catalog,
    objs: Iterable[PlacedObject],
    maps: Sequence[EffortMap],
    resources: Sequence[str],
) -> Promise:
    """The promise reading of the mines among ``objs`` over each player's effort map."""
    mines = _mines(catalog, objs, resources)
    return Promise(tuple({r: effort_to(em, ms) for r, ms in mines.items()} for em in maps))


def promise_ways(
    catalog: Catalog,
    objs: Iterable[PlacedObject],
    maps: Sequence[EffortMap],
    resources: Sequence[str],
) -> dict[int, frozenset[Tile]]:
    """Per level, the tiles each player's hero walks to its nearest mine of each of
    ``resources`` among ``objs``."""
    out: dict[int, set[Tile]] = {}
    for ms in _mines(catalog, objs, resources).values():
        doors_of = [d for o in ms for d in doors(o)]
        for em in maps:
            priced = [
                (e.total, i) for i, d in enumerate(doors_of) if (e := em.visit(d)) is not None
            ]
            if priced:
                for s in em.way(doors_of[min(priced)[1]]):
                    out.setdefault(s.level, set()).add((s.x, s.y))
    return {level: frozenset(tiles) for level, tiles in sorted(out.items())}


def promise_of(
    catalog: Catalog, map_state: MapState, resources: Sequence[str], toll: Sequence[int]
) -> Promise:
    """The promise reading of ``map_state`` for ``resources``, each player priced from its
    own town."""
    maps = player_maps(catalog, map_state, toll)
    return promise_from(catalog, map_state.objs, maps, resources)

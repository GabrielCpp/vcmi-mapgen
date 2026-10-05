"""The price of a cut-off place: the effort a hero spends to carry its reward home, the band
that effort falls in, and how many prizes the place holds by its size."""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState, PlacedObject, Tile
from vcmi_mapgen.core.placement.prizes import HeldPrize
from vcmi_mapgen.core.priors.effort import EffortPriors
from vcmi_mapgen.core.priors.places import PlaceContent, PlaceStats
from vcmi_mapgen.core.reading.content import UNREACHED
from vcmi_mapgen.core.reading.effort import Effort, EffortMap, effort_map
from vcmi_mapgen.core.reading.homes import town_homes
from vcmi_mapgen.core.reading.routes import Spot, route_map
from vcmi_mapgen.core.reading.value import ValueTable, value_of

TILES_PER_PRIZE = 12.0


class UnreachedPlaceError(RuntimeError):
    pass


class Opener(StrEnum):
    """What cuts a place off from the walking map."""

    GATE = "gate"
    SEA = "sea"
    PORTAL = "portal"


@dataclass(frozen=True, slots=True)
class Price:
    """The effort at a place's way in and the band it falls in."""

    effort: Effort
    band: int


@dataclass(frozen=True, slots=True)
class CutoffPlace:
    """A filled cut-off place: what opens it, its price, the prizes placed in it and the
    slots it held back for the set dealer."""

    opener: Opener
    price: Price
    prizes: tuple[PlacedObject, ...]
    held: tuple[HeldPrize, ...] = ()


def homes(map_state: MapState) -> list[Spot]:
    """The visit tiles of every player's starting town."""
    return [s for spots in town_homes(map_state) for s in spots]


def effort_with(
    catalog: Catalog, map_state: MapState, toll: Sequence[int], extra: Sequence[PlacedObject] = ()
) -> EffortMap:
    """The effort map of ``map_state`` with ``extra`` standing on it too."""
    view = MapState(
        size=map_state.size,
        terrain=map_state.terrain,
        gate_blk=map_state.gate_blk,
        objs=[*map_state.objs, *extra],
        player_towns=map_state.player_towns,
    )
    return effort_map(route_map(catalog, view), homes(map_state), toll)


def price_at(em: EffortMap, effort: EffortPriors, spots: Iterable[Spot]) -> Price | None:
    """The cheapest effort over ``spots`` and its band, None when no home reaches one."""
    found = [e for s in spots if (e := em.at(s)) is not None]
    if not found:
        return None
    best = min(found, key=lambda e: e.total)
    return Price(best, effort.band(best.total))


def rewards_in(catalog: Catalog, objs: Iterable[PlacedObject], tiles: Iterable[Tile]) -> int:
    """How many objects of worth stand on ``tiles``."""
    table = ValueTable.of(catalog)
    inside = set(tiles)
    return sum(1 for o in objs if (o.x, o.y) in inside and value_of(catalog, table, o) > 0)


@dataclass(frozen=True, slots=True)
class PrizeCount:
    """How many prizes a cut-off place holds by its area: the corpus median of tiles per
    reward over the places no home reaches on foot."""

    tiles: float = TILES_PER_PRIZE

    @staticmethod
    def of(rows: Iterable[PlaceContent]) -> PrizeCount:
        ratios = [r.area / r.rewards for r in rows if r.hop == UNREACHED and r.rewards > 0]
        return PrizeCount(statistics.median(ratios)) if ratios else PrizeCount()

    def count(self, area: int, held: int = 0) -> int:
        """The prizes still owed to a place of ``area`` tiles that holds ``held``, at least
        one."""
        return max(1, round(area / self.tiles) - held)


def prize_count(stats: Mapping[int, PlaceStats], level: int) -> PrizeCount:
    """The prize count of ``level``, read off its corpus place content, or level 0's when
    the level has none."""
    for lvl in (level, 0):
        found = stats.get(lvl)
        if found is not None and found.content:
            return PrizeCount.of(found.content)
    return PrizeCount()

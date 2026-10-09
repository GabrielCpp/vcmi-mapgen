"""DoorsStep: posts a guard in every door between two territories, then raises the door
guards that leave two enemies under a week apart."""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import replace
from functools import partial
from typing import final, override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Identity, MapState, PlacedObject, Tile
from vcmi_mapgen.core.model.map_state import CoverIndex
from vcmi_mapgen.core.model.payload import Guard
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.core.placement.ground import stands
from vcmi_mapgen.core.placement.guards import guard_spaced
from vcmi_mapgen.core.planning.door_levels import TOP_LEVEL, DoorSpread
from vcmi_mapgen.core.planning.zone_plan import ZonePlan
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.priors.territories import TerritoryStats
from vcmi_mapgen.core.reading.promise import PROMISE_DAYS
from vcmi_mapgen.core.reading.routes import Spot, route_map
from vcmi_mapgen.core.steps.doors.guards import (
    door_caps,
    door_level,
    door_tile,
    open_zones,
    territory_areas,
)
from vcmi_mapgen.core.steps.doors.result import DoorGuard, DoorGuards, ShortPair
from vcmi_mapgen.core.steps.doors.rivals import RivalDoor, cut_rivals, enemy_pairs
from vcmi_mapgen.core.steps.terrain_gen.result import LevelPlaces, PlaceMap
from vcmi_mapgen.core.steps.vegetation.result import LootZones

DOOR_SALT = 0x0D00


@final
class DoorsStep(PipelineStep):
    """Door guards: a random monster stands on one tile of every planned door, so its zone
    of control closes the door. The doors a player crosses before its land holds
    ``HOME_ROOM`` tiles take guards whose tolls leave days to reach its mines. A door into
    a loot zone or a dead-end treasure place stays open. The rival cut then raises the
    guards that leave two enemies under a week apart, home to home, and records the pairs
    it leaves short.

    Config:
        priors  The corpus priors; the step reads the territory spread of each level and
                the guard tolls.
        seed    RNG seed.
        teams   The team of each player, in player order. Players on different teams are
                enemies. Empty makes every player an enemy of every other.

    inject(ctx): ``PlaceMap`` (each level's planned doors and places), ``ZonePlan`` (each
    player's home and the room kept for its town) and ``LootZones`` when present.

    Produces: appends the guards to ``map_state.objs`` and provides ``DoorGuards``, with
    the door spread each level drew.
    """

    def __init__(self, priors: Priors, seed: int = 3, teams: Sequence[int] = ()) -> None:
        self.priors = priors
        self.seed = seed
        self.teams = tuple(teams)
        self.log: list[str] = []
        self._ctx = ProviderRegistry()
        self._places = PlaceMap({})
        self._plan = ZonePlan({}, ())
        self._loot = LootZones()
        self._spreads: dict[int, DoorSpread] = {}

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx
        self._places = ctx.get(PlaceMap, PlaceMap({}))
        self._plan = ctx.get(ZonePlan, ZonePlan({}, ()))
        self._loot = ctx.get(LootZones, LootZones())

    @override
    def run(self, catalog: Catalog, map_state: MapState) -> None:
        rng = random.Random(self.seed ^ DOOR_SALT)
        drawn: list[tuple[DoorGuard, int]] = []
        for level, lp in sorted(self._places.levels.items()):
            drawn += self._post(catalog, map_state, level, lp, rng)
        doors = [RivalDoor(Spot(g.level, *g.tile), g.guard_level, cap) for g, cap in drawn]
        pairs = enemy_pairs(len(self._plan.player_zids), self.teams)
        toll = self.priors.effort.toll
        cut = cut_rivals(route_map(catalog, map_state), toll, doors, self._homes(), pairs)
        posted = [_raise(catalog, g, lv) for (g, _), lv in zip(drawn, cut.levels, strict=True)]
        self.log += [_short_line(p) for p in cut.short]
        map_state.add_objs([d.obj for d in posted])
        for line in self.log:
            print(f"  WARNING: {line}")
        self._ctx.provide(DoorGuards(tuple(posted), cut.short, self._spreads))

    def _homes(self) -> dict[int, Spot]:
        homes: dict[int, Spot] = {}
        for player, (level, zid) in enumerate(self._plan.player_zids):
            zone = self._plan.levels[level].zones.get(zid)
            if zone is not None and zone.town.path:
                homes[player] = Spot(level, *zone.town.path[0])
        return homes

    def _post(
        self,
        catalog: Catalog,
        map_state: MapState,
        level: int,
        lp: LevelPlaces,
        rng: random.Random,
    ) -> list[tuple[DoorGuard, int]]:
        spread = DoorSpread.draw(self.priors.territories.get(level, TerritoryStats()), rng)
        self._spreads[level] = spread
        plan = lp.territories
        skip = open_zones(lp.places, self._loot.on(level), plan.doors)
        areas = territory_areas(lp.label, plan.zones)
        caps = door_caps(plan, areas, self.priors.effort.toll, PROMISE_DAYS)
        post = _Post(catalog, map_state, level)
        posted: list[tuple[DoorGuard, int]] = []
        for i, door in enumerate(plan.doors):
            if any(z in skip for z in door.zones):
                continue
            cap = caps.get(i, TOP_LEVEL)
            strength = door_level(spread, door, rng, cap)
            ident = catalog.guard(strength)
            tile = door_tile(door, partial(post.fits, ident))
            if tile is None:
                self.log.append(f"door guard: L{level} door {door.tiles[0]} takes no guard")
                continue
            guard = DoorGuard(level, door.zones, tile, strength, post.add(ident, tile))
            posted.append((guard, cap))
        return posted


def _guard_obj(ident: Identity, tile: Tile, level: int) -> PlacedObject:
    return PlacedObject.at(ident, tile, level=level, purpose=Purpose.GUARD, payload=Guard())


def _raise(catalog: Catalog, guard: DoorGuard, level: int) -> DoorGuard:
    if level == guard.guard_level:
        return guard
    obj = _guard_obj(catalog.guard(level), guard.tile, guard.level)
    return replace(guard, guard_level=level, obj=obj, raised=level - guard.guard_level)


def _short_line(pair: ShortPair) -> str:
    a, b = pair.players
    return f"rival cut: P{a} and P{b} stay {pair.days} hero-days apart: {pair.reason}"


@final
class _Post:
    """One level's objects as the door guards land among them."""

    def __init__(self, catalog: Catalog, map_state: MapState, level: int) -> None:
        objs = [o for o in map_state.objs if o.level == level]
        self.catalog = catalog
        self.level = level
        self.ground = map_state.terrain.get(level, ())
        self.cover = CoverIndex(objs)
        self.guards = [(o.x, o.y) for o in objs if o.purpose == Purpose.GUARD]

    def fits(self, ident: Identity, tile: Tile) -> bool:
        probe = PlacedObject.at(ident, tile, level=self.level, purpose=Purpose.GUARD)
        return (
            stands(self.catalog, ident, tile, self.ground)
            and guard_spaced(tile, self.guards)
            and self.cover.accepts(probe)
        )

    def add(self, ident: Identity, tile: Tile) -> PlacedObject:
        obj = _guard_obj(ident, tile, self.level)
        self.cover.add(obj)
        self.guards.append(tile)
        return obj

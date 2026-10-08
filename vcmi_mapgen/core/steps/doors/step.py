"""DoorsStep: posts a guard in every door between two territories."""

from __future__ import annotations

import random
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
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.priors.territories import TerritoryStats
from vcmi_mapgen.core.reading.promise import PROMISE_DAYS
from vcmi_mapgen.core.steps.doors.guards import (
    TOP_LEVEL,
    DoorSpread,
    door_caps,
    door_level,
    door_tile,
    open_zones,
    territory_areas,
)
from vcmi_mapgen.core.steps.doors.result import DoorGuard, DoorGuards
from vcmi_mapgen.core.steps.terrain_gen.result import LevelPlaces, PlaceMap
from vcmi_mapgen.core.steps.vegetation.result import LootZones

DOOR_SALT = 0x0D00


@final
class DoorsStep(PipelineStep):
    """Door guards: a random monster stands on one tile of every planned door, so its zone
    of control closes the door. The doors a player crosses before its land holds
    ``HOME_ROOM`` tiles take guards whose tolls leave days to reach its mines. A door into
    a loot zone or a dead-end treasure place stays open.

    Config:
        priors  The corpus priors; the step reads the territory spread of each level.
        seed    RNG seed.

    inject(ctx): ``PlaceMap`` (each level's planned doors and places) and ``LootZones``
    when present.

    Produces: appends the guards to ``map_state.objs`` and provides ``DoorGuards``.
    """

    def __init__(self, priors: Priors, seed: int = 3) -> None:
        self.priors = priors
        self.seed = seed
        self.log: list[str] = []
        self._ctx = ProviderRegistry()
        self._places = PlaceMap({})
        self._loot = LootZones()

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx
        self._places = ctx.get(PlaceMap, PlaceMap({}))
        self._loot = ctx.get(LootZones, LootZones())

    @override
    def run(self, catalog: Catalog, map_state: MapState) -> None:
        rng = random.Random(self.seed ^ DOOR_SALT)
        posted: list[DoorGuard] = []
        for level, lp in sorted(self._places.levels.items()):
            posted += self._post(catalog, map_state, level, lp, rng)
        map_state.add_objs([d.obj for d in posted])
        for line in self.log:
            print(f"  WARNING: {line}")
        self._ctx.provide(DoorGuards(tuple(posted)))

    def _post(
        self,
        catalog: Catalog,
        map_state: MapState,
        level: int,
        lp: LevelPlaces,
        rng: random.Random,
    ) -> list[DoorGuard]:
        spread = DoorSpread.draw(self.priors.territories.get(level, TerritoryStats()), rng)
        plan = lp.territories
        skip = open_zones(lp.places, self._loot.on(level), plan.doors)
        areas = territory_areas(lp.label, plan.zones)
        caps = door_caps(plan, areas, self.priors.effort.toll, PROMISE_DAYS)
        post = _Post(catalog, map_state, level)
        posted: list[DoorGuard] = []
        for i, door in enumerate(plan.doors):
            if any(z in skip for z in door.zones):
                continue
            strength = door_level(spread, door, rng, caps.get(i, TOP_LEVEL))
            ident = catalog.guard(strength)
            tile = door_tile(door, partial(post.fits, ident))
            if tile is None:
                self.log.append(f"door guard: L{level} door {door.tiles[0]} takes no guard")
                continue
            posted.append(DoorGuard(level, door.zones, tile, strength, post.add(ident, tile)))
        return posted


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
        obj = PlacedObject.at(ident, tile, level=self.level, purpose=Purpose.GUARD, payload=Guard())
        self.cover.add(obj)
        self.guards.append(tile)
        return obj

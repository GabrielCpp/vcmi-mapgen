"""Islands: the land places no home reaches on foot that a hero reaches by boat. Each island
holds prizes by its size, every prize beside the one guard in front of it, drawn from the
band of the effort to carry it home."""

from __future__ import annotations

import random
from collections.abc import Container, Mapping, Sequence
from dataclasses import dataclass, field

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.geometry import NB8
from vcmi_mapgen.core.model import CoverIndex, PlacedObject, PlacementRule, Tile, Zone
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.placement.guards import guard_spaced, guard_zoc
from vcmi_mapgen.core.placement.place import PlaceSpec, PlaceTarget, place_one
from vcmi_mapgen.core.placement.prizes import PrizePools, place_prizes
from vcmi_mapgen.core.planning.guarding import PrizeGuard
from vcmi_mapgen.core.planning.pricing import (
    CutoffPlace,
    Opener,
    PrizeCount,
    UnreachedPlaceError,
    price_at,
    rewards_in,
)
from vcmi_mapgen.core.planning.zone_index import ZoneRecord
from vcmi_mapgen.core.priors.effort import EffortPriors
from vcmi_mapgen.core.priors.gameplay import GameplayStats
from vcmi_mapgen.core.reading.effort import EffortMap
from vcmi_mapgen.core.reading.routes import Spot

ISLAND_MIN_AREA = 12
PRIZES_PER_GUARD = 3


@dataclass(frozen=True, slots=True)
class IslandLevel:
    """One level's inputs: its zones and zone records, the loot zones a gate already opens,
    the objects on it, the gameplay statistics per terrain, the prize guard and prize count,
    and the claims and rules every new object must pass."""

    level: int
    zones: Mapping[int, Zone]
    records: Sequence[ZoneRecord]
    loot: Container[int]
    objs: Sequence[PlacedObject]
    gameplay: GameplayStats
    guard: PrizeGuard
    count: PrizeCount
    claims: frozenset[Tile] = frozenset()
    rules: Sequence[PlacementRule] = ()


@dataclass(frozen=True, slots=True)
class Island:
    """A land place a hero reaches only by boat: its record, the tiles a hero reaches on it
    and how many prizes it still owes."""

    record: ZoneRecord
    reach: frozenset[Tile]
    owed: int


@dataclass(slots=True)
class GuardedIsland:
    """An island with its guards placed: each guard and the ring tiles its prizes take."""

    island: Island
    rings: list[tuple[PlacedObject, list[Tile]]] = field(
        default_factory=list[tuple[PlacedObject, list[Tile]]]
    )

    def slots(self) -> list[Tile]:
        return [t for _g, ring in self.rings for t in ring]


def find_islands(
    catalog: Catalog, lvl: IslandLevel, em: EffortMap, reached: Container[tuple[int, int, int]]
) -> list[Island]:
    """Every land zone of at least ``ISLAND_MIN_AREA`` tiles that no home reaches on foot,
    no gate opens, and a hero still reaches over water. A zone no hero reaches at all is
    left to the portal rescue."""
    out: list[Island] = []
    for zr in lvl.records:
        z = lvl.zones.get(zr.zid)
        if z is None or z.terrain_type.is_barrier or z.area < ISLAND_MIN_AREA:
            continue
        if zr.zid in lvl.loot or any((x, y, lvl.level) in reached for x, y in z.tiles_set):
            continue
        reach = frozenset(t for t in zr.passable if em.at(Spot(lvl.level, *t)) is not None)
        if reach:
            held = rewards_in(catalog, lvl.objs, zr.ts)
            out.append(Island(zr, reach, lvl.count.count(z.area, held)))
    return out


def _ring(t: Tile, reach: Container[Tile], blocked: Container[Tile]) -> list[Tile]:
    return [s for dx, dy in NB8 if (s := (t[0] + dx, t[1] + dy)) in reach and s not in blocked]


@dataclass(slots=True)
class _Guarding:
    """The guards a level already holds: their tiles for spacing and their zone of control."""

    tiles: list[Tile]
    zoc: set[Tile]

    @staticmethod
    def of(objs: Sequence[PlacedObject]) -> _Guarding:
        tiles = [
            c
            for o in objs
            if o.purpose == Purpose.GUARD
            for c in FP.interactive_cells(o.footprint, o.x, o.y)
        ]
        return _Guarding(tiles, guard_zoc(objs))


def guard_island(
    target: PlaceTarget, island: Island, guard: PrizeGuard, guarding: _Guarding
) -> GuardedIsland:
    """Guards on ``island`` until their free ring tiles cover the prizes it owes, the guard
    with the most free ring tiles first. Each guard keeps up to ``PRIZES_PER_GUARD`` ring
    tiles for its prizes, none inside another guard's zone of control."""
    out = GuardedIsland(island)
    rng, cover, zid = target.rng, target.cover, island.record.zid
    tiles = sorted(island.reach)
    rng.shuffle(tiles)
    blocked = cover.claims | guarding.zoc
    tiles.sort(key=lambda t: -len(_ring(t, island.reach, blocked)))
    owed = island.owed
    for t in tiles:
        if owed <= 0:
            break
        blocked = cover.claims | guarding.zoc
        ring = _ring(t, island.reach, blocked)[:PRIZES_PER_GUARD]
        if not ring or t in blocked or not guard_spaced(t, guarding.tiles):
            continue
        ident = target.catalog.guard(guard.level(rng, zid))
        spec = PlaceSpec(Purpose.GUARD, None, ident=ident, interactive_only=True)
        if not place_one(target, spec, *t):
            continue
        g = target.objs[-1]
        guarding.tiles.append(t)
        guarding.zoc |= guard_zoc([g])
        ring = [s for s in ring if s not in cover.claims][:owed]
        if ring:
            out.rings.append((g, ring))
            owed -= len(ring)
    return out


@dataclass(slots=True)
class IslandFill:
    """One level's islands, guarded first and filled once the effort map sees their guards."""

    lvl: IslandLevel
    cover: CoverIndex
    seed: int
    bounds: tuple[int, int] | None
    guarded: list[GuardedIsland] = field(default_factory=list[GuardedIsland])

    def guard(
        self, catalog: Catalog, em: EffortMap, reached: Container[tuple[int, int, int]]
    ) -> list[PlacedObject]:
        """Find the level's islands on ``em`` and place their guards. Returns the guards."""
        guarding = _Guarding.of(self.lvl.objs)
        for island in find_islands(catalog, self.lvl, em, reached):
            zr = island.record
            rng = random.Random(self.seed ^ (self.lvl.level * 7919) ^ (zr.zid * 104729) ^ 0x15A4D)
            objs: list[PlacedObject] = []
            st = self.lvl.gameplay[zr.terrain]
            target = PlaceTarget(catalog, objs, self.cover, island.reach, rng, st, self.bounds)
            g = guard_island(target, island, self.lvl.guard, guarding)
            for o in objs:
                o.level = self.lvl.level
            if g.rings:
                self.guarded.append(g)
        return [g for isl in self.guarded for g, _ring in isl.rings]

    def fill(
        self, catalog: Catalog, em: EffortMap, effort: EffortPriors
    ) -> tuple[dict[int, CutoffPlace], list[PlacedObject]]:
        """Price every guarded island on ``em`` and place its prizes on its guards' rings.
        Returns each island's place and every object kept, guards with no prize left out."""
        places: dict[int, CutoffPlace] = {}
        kept: list[PlacedObject] = []
        for isl in self.guarded:
            zr = isl.island.record
            slots = isl.slots()
            price = price_at(em, effort, (Spot(self.lvl.level, *t) for t in slots))
            if price is None:
                raise UnreachedPlaceError(
                    f"no home reaches island {zr.zid} on level {self.lvl.level}"
                )
            rng = random.Random(self.seed ^ (self.lvl.level * 7919) ^ (zr.zid * 104729) ^ 0x15A4E)
            objs: list[PlacedObject] = []
            st = self.lvl.gameplay[zr.terrain]
            target = PlaceTarget(catalog, objs, self.cover, frozenset(slots), rng, st, self.bounds)
            pools = PrizePools.of(catalog, zr.terrain)
            prizes = place_prizes(target, pools, effort.offer(price.band), slots, len(slots))
            took = prizes.took()
            for o in objs:
                o.level = self.lvl.level
            guards = [g for g, ring in isl.rings if took.intersection(ring)]
            kept.extend([*guards, *objs])
            held = (prizes.held.at(self.lvl.level, zr.terrain),) if prizes.held else ()
            places[zr.zid] = CutoffPlace(Opener.SEA, price, tuple(objs), held)
        return places, kept

"""GameplayStep: the player-zone pick, the sea objects, then every gameplay object placed
against the vegetated field, in order: gate pairs, player towns, shipyards, each player
town's own sawmill and ore pit, the accent landmarks, the promised mines, then one map-wide
pass over the neutral towns with their own sawmill and ore pit, mines, dwellings, banks and
visitables. The pass holds each family at the corpus rate per tile, and
the objects already standing count inside it. A town may cover the zone's entrance bands and
spill onto vegetation beyond it. Every player town is protected from then on, so no later
object guards its entrance or walls in its start."""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import final, override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Identity, MapState, PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.core.placement.guards import inflate_gap
from vcmi_mapgen.core.placement.keep_out import KeepOutRule
from vcmi_mapgen.core.placement.site import (
    HOME_FOOTING,
    LevelField,
    PlacedZone,
    SiteIndex,
    SiteZone,
    ZoneSite,
)
from vcmi_mapgen.core.placement.start_room import StartRoomRule
from vcmi_mapgen.core.placement.ways import WayRule
from vcmi_mapgen.core.planning import zone_plan as ZPL
from vcmi_mapgen.core.planning.content import ContentPlan
from vcmi_mapgen.core.planning.pricing import effort_with
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.reading.effort import EffortMap
from vcmi_mapgen.core.reading.families import Families, unguarded
from vcmi_mapgen.core.reading.homes import town_homes
from vcmi_mapgen.core.reading.mines import BASIC_MINE_RES, MapMeasure, land_area
from vcmi_mapgen.core.reading.paint import Accent
from vcmi_mapgen.core.reading.promise import (
    player_maps,
    promise_from,
    promise_ways,
)
from vcmi_mapgen.core.reading.routes import route_map
from vcmi_mapgen.core.reading.supply import supply_gaps
from vcmi_mapgen.core.steps.gameplay.allocate import Kept, Pricer, keep_promise, site_variants
from vcmi_mapgen.core.steps.gameplay.economy import tie_dwellings
from vcmi_mapgen.core.steps.gameplay.gate_pairs import place_gate_pairs
from vcmi_mapgen.core.steps.gameplay.landmark import (
    LANDMARK_FLOOR,
    dragon_order,
    place_dragon,
    place_landmarks,
)
from vcmi_mapgen.core.steps.gameplay.pick import Picker
from vcmi_mapgen.core.steps.gameplay.placer import Demand, Placement
from vcmi_mapgen.core.steps.gameplay.result import (
    GameplayResult,
    GateResult,
    PromisedWays,
    TownsIndex,
)
from vcmi_mapgen.core.steps.gameplay.sea_links import SeaLinks, sea_way
from vcmi_mapgen.core.steps.gameplay.shipyards import Link, Shore, place_link, place_shipyards
from vcmi_mapgen.core.steps.gameplay.siting import TOWN_MIN_AREA
from vcmi_mapgen.core.steps.gameplay.supply import stand_pairs
from vcmi_mapgen.core.steps.terrain_gen.result import Accents, Segmentation
from vcmi_mapgen.core.steps.vegetation.result import LootZones, VegetationResult

NO_TILES: frozenset[Tile] = frozenset()
PLACER_SALT = 0x61A7


def _sites(indexes: dict[int, SiteIndex], loot: LootZones) -> list[ZoneSite]:
    return [
        s
        for level, idx in sorted(indexes.items())
        for zid, s in sorted(idx.sites.items())
        if zid not in loot.on(level)
    ]


def _town_hosts(sites: Sequence[ZoneSite]) -> list[ZoneSite]:
    free = [s for s in sites if s.town_center is None and len(s.zone.ts) >= TOWN_MIN_AREA]
    shared = [s for s in sites if s.town_center is not None and len(s.zone.ts) >= 4 * TOWN_MIN_AREA]
    return [
        *sorted(free, key=lambda s: -len(s.zone.ts)),
        *sorted(shared, key=lambda s: -len(s.zone.ts)),
    ]


def _town_order(site: ZoneSite, ident: Identity) -> list[Tile]:
    if site.town_center is None:
        return site.centroid_order(ident)
    cx, cy = site.town_center
    return sorted(site.ts, key=lambda t: (-((t[0] - cx) ** 2 + (t[1] - cy) ** 2), t))


@final
class GameplayStep(PipelineStep):
    """Place every gameplay object once vegetation has grown.

    Config:
        priors      The corpus priors; the step reads the gameplay statistics and the gate
                    estimator.
        seed        RNG seed.
        players     Number of player zones to designate (0 = neutral map).
        subterrain  Whether a second underground level is active.
        density     The multiplier on the corpus rate of gameplay objects per tile.

    inject(ctx): ``ZonePlan`` (each zone's plan, the player zones and the sea objects),
    ``VegetationResult`` (each zone's open and walkable tiles), ``Segmentation`` (the surface
    zones), and the ``ContentPlan`` when present: a planned home's town may lay its overlay
    outside the zone. The ``Accents`` when present: each accent patch of ``LANDMARK_FLOOR``
    tiles or more takes a landmark right after the towns, and the map-wide pass counts it.
    The patch the homes reach last takes a dragon dwelling behind a level-7 guard instead.
    The ``LootZones`` when present: no object stands in a zone chosen to be sealed.
    The step publishes the player zones the zone plan picked, then commits the sea objects
    the zone plan drew. Gates stay off each player town's kept room.
    A player town that finds no spot in its zone moves to the largest zone with room for it.

    A player apart from a rival by land gets a shipyard whose sea lands on that rival's land,
    right after the shipyards of the zone plan, and the step warns when none fits. From then
    on no object closes the land tiles of its way to the rival town.

    Every town owns a sawmill and an ore pit within ``NEAR`` tiles, stood right after the
    towns and before any other mine near them, and the step warns about a town left short.

    Each player should reach a mine of each basic resource within ``PROMISE_DAYS``
    hero-days, and the step warns when one does not: the promised mines stand before the
    map-wide pass, and a repair pass after it adds any mine a player lost. The pass spreads
    each family evenly between the players band by band, and ``density`` multiplies its
    corpus rate. From the promised mines on, no object closes a player's way to its nearest
    mine of each resource.

    Produces: appends the objects to ``map_state.objs``, sets ``map_state.gate_blk`` and
    ``map_state.player_towns``. Into ctx: ``TownsIndex``, ``GateResult``, ``GameplayResult``
    and ``PromisedWays``.
    """

    def __init__(
        self,
        priors: Priors,
        seed: int = 3,
        players: int = 0,
        subterrain: bool = False,
        density: float = 1.0,
    ) -> None:
        self.priors = priors
        self.seed = seed
        self.players = players
        self.subterrain = subterrain
        self.density = density
        self.objs: list[PlacedObject] = []
        self._log: list[str] = []
        self._ctx = ProviderRegistry()
        self._plan = ZPL.ZonePlan({}, ())
        self._veg = VegetationResult()
        self._grids: dict[int, list[list[Terrain]]] = {}
        self._segmentation = Segmentation({}, {})
        self._player_zids: list[tuple[int, int]] = []
        self._starts: dict[int, StartRoomRule] = {}
        self._ways: dict[int, WayRule] = {}
        self._content = ContentPlan()
        self._accents = Accents()
        self._loot = LootZones()
        self._sea_ways: dict[int, frozenset[Tile]] = {}

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx
        self._plan = ctx.require(ZPL.ZonePlan)
        self._veg = ctx.require(VegetationResult)
        self._segmentation = ctx.require(Segmentation)
        self._content = ctx.get(ContentPlan, ContentPlan())
        self._accents = ctx.get(Accents, Accents())
        self._loot = ctx.get(LootZones, LootZones())

    @override
    def run(self, catalog: Catalog, map_state: MapState) -> None:
        self._grids = map_state.terrain
        self._pick_player_zones()
        for _level, pl in sorted(self._plan.levels.items()):
            map_state.add_objs(list(pl.sea))
        indexes = {
            level: self._index(catalog, level, map_state) for level in sorted(self._plan.levels)
        }
        gates = self._place_gates(catalog, indexes, map_state)
        self._place_player_towns(catalog, indexes)
        if 0 in indexes:
            self._place_shipyards(indexes[0], map_state, catalog)
            self._link_starts(catalog, indexes, map_state)
        sites = _sites(indexes, self._loot)
        towns = [o for s in sites for o in s.objs if o.purpose == Purpose.TOWN]
        _ = stand_pairs(sites, site_variants(catalog), towns)
        self._place_landmarks(catalog, indexes, map_state)
        for line in self._keep_promise(catalog, indexes, map_state).warnings:
            print(f"  WARNING: mine promise: {line}")
        if 0 in indexes:
            indexes[0].lf.avoid = NO_TILES
        self._place_all(catalog, indexes, map_state)
        for line in self._keep_promise(catalog, indexes, map_state).warnings:
            print(f"  WARNING: mine promise repair: {line}")
        self._finish(catalog, indexes, map_state)
        for line in supply_gaps(catalog, map_state.objs):
            print(f"  WARNING: town supply: {line}")
        self._read_promise(catalog, map_state)
        self._ctx.provide(gates)

    def _read_promise(self, catalog: Catalog, map_state: MapState) -> None:
        maps = player_maps(catalog, map_state, self.priors.effort.toll)
        for line in promise_from(catalog, map_state.objs, maps, BASIC_MINE_RES).broken():
            print(f"  WARNING: mine promise broken: {line}")
        ways = promise_ways(catalog, map_state.objs, maps, BASIC_MINE_RES)
        sea = self._sea_ways
        kept = {lv: ways.get(lv, NO_TILES) | sea.get(lv, NO_TILES) for lv in {*ways, *sea}}
        self._ctx.provide(PromisedWays(kept))

    def _place_landmarks(
        self, catalog: Catalog, indexes: dict[int, SiteIndex], map_state: MapState
    ) -> None:
        dragon = self._place_dragon(catalog, indexes, map_state)
        for level, idx in sorted(indexes.items()):
            patches = self._accents.levels.get(level, ())
            skip = dragon[1] if dragon is not None and dragon[0] == level else None
            for _zid, site in sorted(idx.sites.items()):
                _ = place_landmarks(site, patches, self.seed, skip)

    def _place_all(
        self, catalog: Catalog, indexes: dict[int, SiteIndex], map_state: MapState
    ) -> None:
        sites = _sites(indexes, self._loot)
        homes = self._view(indexes, map_state).player_towns
        measure = MapMeasure(land_area(map_state), len(homes))
        demand = Demand(measure, self.priors.mines, self.priors.towns, self.density)
        rng = random.Random(self.seed ^ PLACER_SALT)
        toll = self.priors.effort.toll
        families = Families.of(catalog)

        def price() -> list[EffortMap]:
            view = self._view(indexes, map_state)
            objs = [o for o in view.objs if families.family(catalog, o) is not None]
            return player_maps(catalog, unguarded(catalog, view, objs), toll)

        placement = Placement(catalog, sites, self.priors.effort, demand, rng)
        sea = [o for _level, pl in sorted(self._plan.levels.items()) for o in pl.sea]
        plan = placement.plan(homes, sea, price())
        has_water = any(Terrain.WATER in row for grid in self._grids.values() for row in grid)
        picker = Picker(catalog, rng, has_water, self.subterrain)
        variants = site_variants(catalog)
        short = placement.place(plan, picker, price, lambda new: stand_pairs(sites, variants, new))
        self._log += [f"WARNING: gameplay shortfall: {line}" for line in short.lines()]

    def _keep_promise(
        self, catalog: Catalog, indexes: dict[int, SiteIndex], map_state: MapState
    ) -> Kept:
        sites = _sites(indexes, self._loot)
        kept = keep_promise(
            sites, site_variants(catalog), lambda: self._survey(catalog, indexes, map_state)
        )
        if kept.stood:
            _ = self._survey(catalog, indexes, map_state)
        return kept

    def _survey(
        self, catalog: Catalog, indexes: dict[int, SiteIndex], map_state: MapState
    ) -> tuple[Pricer, dict[str, tuple[int | None, ...]]]:
        view = self._view(indexes, map_state)
        maps = player_maps(catalog, view, self.priors.effort.toll)
        for level, tiles in promise_ways(catalog, view.objs, maps, BASIC_MINE_RES).items():
            if level in self._ways:
                self._ways[level].keep(tiles)
        have = promise_from(catalog, view.objs, maps, BASIC_MINE_RES)
        return Pricer(maps), {r: tuple(d[r] for d in have.days) for r in BASIC_MINE_RES}

    def _view(self, indexes: dict[int, SiteIndex], map_state: MapState) -> MapState:
        objs = [o for idx in indexes.values() for site in idx.sites.values() for o in site.objs]
        towns: dict[tuple[int, int], list[PlacedObject]] = {}
        for level, idx in sorted(indexes.items()):
            for zid, site in sorted(idx.sites.items()):
                zone_towns = [o for o in site.objs if o.purpose == Purpose.TOWN]
                if zone_towns:
                    towns[level, zid] = zone_towns
        return MapState(
            size=map_state.size,
            terrain=map_state.terrain,
            gate_blk=map_state.gate_blk,
            objs=[*map_state.objs, *objs],
            player_towns=self._player_towns(towns),
        )

    def _pick_player_zones(self) -> None:
        self._player_zids = list(self._plan.player_zids)
        self._ctx.provide(TownsIndex(player_zids=self._player_zids))

    def _place_gates(
        self, catalog: Catalog, indexes: dict[int, SiteIndex], map_state: MapState
    ) -> GateResult:
        landings = self._landings() if 0 in indexes else set[Tile]()
        for level, idx in indexes.items():
            rooms = (zone.town.cells for zone in self._plan.levels[level].zones.values())
            idx.lf.avoid = frozenset[Tile]().union(*rooms) | (landings if level == 0 else NO_TILES)
        gates = GateResult()
        if self.subterrain and 0 in indexes and 1 in indexes:
            pair = (indexes[0], indexes[1])
            gates = place_gate_pairs(catalog, pair, self.priors.gates, map_state.size, self.seed)
        for level, idx in indexes.items():
            idx.lf.avoid = landings if level == 0 else NO_TILES
        map_state.gate_blk = gates.gate_blk
        return gates

    def _place_player_towns(self, catalog: Catalog, indexes: dict[int, SiteIndex]) -> None:
        for level, zid in sorted(self._player_zids):
            idx = indexes.get(level)
            site = idx.sites.get(zid) if idx is not None else None
            if site is None:
                continue
            ident = catalog.random_town()
            footing = HOME_FOOTING if (level, zid) in self._content.homes else None
            town = site.place(Purpose.TOWN, ident, site.centroid_order(ident), footing)
            if town is None:
                print(f"  WARNING: player zone {zid} (level {level}) could not fit its town")
            else:
                self._starts[level].protect(town)
        self._move_player_towns(catalog, indexes)

    def _move_player_towns(self, catalog: Catalog, indexes: dict[int, SiteIndex]) -> None:
        sites = _sites(indexes, self._loot)
        need = self.players - sum(1 for s in sites if s.town_center is not None)
        ident = catalog.random_town()
        for site in _town_hosts(sites):
            if need <= 0:
                return
            town = site.place(Purpose.TOWN, ident, _town_order(site, ident))
            if town is not None:
                self._starts[site.lf.level].protect(town)
                need -= 1
                print(f"  player town moved to zone {site.zid} (level {site.lf.level})")
        if need > 0:
            print(f"  WARNING: {need} player town(s) found no zone with room")

    def _place_dragon(
        self, catalog: Catalog, indexes: dict[int, SiteIndex], map_state: MapState
    ) -> tuple[int, Accent] | None:
        if not any(p.size >= LANDMARK_FLOOR for ps in self._accents.levels.values() for p in ps):
            return None
        view = self._view(indexes, map_state)
        em = effort_with(catalog, view, self.priors.effort.toll)
        sites = {(lv, z): s for lv, idx in indexes.items() for z, s in idx.sites.items()}
        return place_dragon(sites, dragon_order(self._accents.levels, em.at), self.seed)

    def _landings(self) -> set[Tile]:
        planned = self._plan.levels[0].landings
        landing: set[Tile] = set()
        inflate_gap(landing, planned.blk | planned.appr)
        return landing

    def _index(
        self,
        catalog: Catalog,
        level: int,
        map_state: MapState,
    ) -> SiteIndex:
        self._starts[level] = StartRoomRule(map_state, level)
        self._ways[level] = WayRule()
        lf = LevelField.build(
            level,
            self._grids[level],
            [o for o in map_state.objs if o.level == level],
            rules=(self._starts[level], self._ways[level], KeepOutRule(self._loot_tiles(level))),
        )
        idx = SiteIndex(lf)
        vegetated = self._veg.zones[level]
        for zid, zone in sorted(self._plan.levels[level].zones.items()):
            v = vegetated[zid]
            st = self.priors.gameplay[level][zone.terrain]
            site = SiteZone(
                zone.terrain, st, zone.ts, zone.ent_bands, zone.prot, v.open_set, v.passable
            )
            idx.sites[zid] = ZoneSite(catalog, zid, site, lf, self.seed)
            idx.zone_of.update(dict.fromkeys(zone.ts, zid))
        return idx

    def _loot_tiles(self, level: int) -> frozenset[Tile]:
        zones = self._plan.levels[level].zones
        return frozenset[Tile]().union(*(zones[zid].ts for zid in self._loot.on(level)))

    def _shore(self, idx: SiteIndex, map_state: MapState) -> Shore:
        objs = [o for o in map_state.objs if o.level == 0 and o.purpose]
        objs += [o for site in idx.sites.values() for o in site.objs]
        return Shore(self._grids[0], self._segmentation.zones[0], objs)

    def _place_shipyards(self, idx: SiteIndex, map_state: MapState, catalog: Catalog) -> None:
        avoid, idx.lf.avoid = idx.lf.avoid, NO_TILES
        n = place_shipyards(idx, self._shore(idx, map_state), self.seed, catalog)
        idx.lf.avoid = avoid
        print(f"  L0 seaport guarantee: {n} shipyard(s) added")

    def _link_starts(
        self, catalog: Catalog, indexes: dict[int, SiteIndex], map_state: MapState
    ) -> None:
        idx = indexes[0]
        links = self._sea_links(catalog, indexes, map_state)
        for a, b in links.unlinked():
            if links.joined(a, b) or links.linked(a, b):
                continue
            if self._link(catalog, idx, map_state, links, (a, b)) is None:
                print(f"  WARNING: player {a} has no shipyard that sails to player {b}")
                continue
            links = self._sea_links(catalog, indexes, map_state)
        self._keep_sea_ways(catalog, indexes, map_state, links)

    def _sea_links(
        self, catalog: Catalog, indexes: dict[int, SiteIndex], map_state: MapState
    ) -> SeaLinks:
        view = self._view(indexes, map_state)
        return SeaLinks(route_map(catalog, view), town_homes(view))

    def _link(
        self,
        catalog: Catalog,
        idx: SiteIndex,
        map_state: MapState,
        links: SeaLinks,
        pair: tuple[int, int],
    ) -> PlacedObject | None:
        a, b = pair
        avoid, idx.lf.avoid = idx.lf.avoid, NO_TILES
        placed = None
        for ceiling in (0, None):
            home = links.land(a, ceiling)
            tiles = {(s.x, s.y) for s in home if s.level == 0}
            shore = self._shore(idx, map_state)
            placed = place_link(idx, shore, self.seed, catalog, Link(tiles, links.fit(b, home)))
            if placed is not None:
                break
        idx.lf.avoid = avoid
        return placed

    def _keep_sea_ways(
        self,
        catalog: Catalog,
        indexes: dict[int, SiteIndex],
        map_state: MapState,
        links: SeaLinks,
    ) -> None:
        apart = links.apart()
        if not apart:
            return
        view = self._view(indexes, map_state)
        maps = player_maps(catalog, view, self.priors.effort.toll)
        route = links.route
        ways: dict[int, set[Tile]] = {}
        for a, b in apart:
            for s in sea_way(maps[a], links.homes[b]):
                if not route.water[s.level][s.y][s.x]:
                    ways.setdefault(s.level, set()).add((s.x, s.y))
        for level, tiles in ways.items():
            if level in self._ways:
                self._ways[level].keep(tiles)
        self._sea_ways = {level: frozenset(tiles) for level, tiles in ways.items()}

    def _finish(
        self,
        catalog: Catalog,
        indexes: dict[int, SiteIndex],
        map_state: MapState,
    ) -> None:
        towns: dict[tuple[int, int], list[PlacedObject]] = {}
        zones: dict[int, dict[int, PlacedZone]] = {}
        landings: dict[int, ZPL.Landings] = {}
        town_of_zone: dict[int, dict[int, PlacedObject]] = {}
        for level, idx in sorted(indexes.items()):
            zones[level] = {}
            town_of_zone[level] = {}
            for zid, site in sorted(idx.sites.items()):
                zones[level][zid] = site.placed()
                self.objs.extend(site.objs)
                zone_towns = [o for o in site.objs if o.purpose == Purpose.TOWN]
                if zone_towns:
                    town_of_zone[level][zid] = zone_towns[0]
                    towns[level, zid] = zone_towns
            blk, appr = ZPL.seaport_cells(
                catalog,
                [o for o in [*map_state.objs, *self.objs] if o.level == level],
            )
            landings[level] = ZPL.Landings(frozenset(blk), frozenset(appr))
        map_state.add_objs(self.objs)
        map_state.player_towns = self._player_towns(towns)
        tie_dwellings(catalog, map_state, self.priors.effort.toll)
        self._ctx.provide(GameplayResult(zones, landings, town_of_zone, tuple(self._log)))

    def _player_towns(self, towns: dict[tuple[int, int], list[PlacedObject]]) -> list[PlacedObject]:
        out = [towns[k][0] for k in self._player_zids if k in towns]
        if not self.players:
            return out
        spare: Sequence[PlacedObject] = [
            t for zone_towns in towns.values() for t in zone_towns if t not in out
        ]
        out += spare[: max(0, self.players - len(out))]
        return out[: self.players]

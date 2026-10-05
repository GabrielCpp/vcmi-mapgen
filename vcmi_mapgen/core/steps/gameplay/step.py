"""GameplayStep: the player-zone pick, the sea objects, then every gameplay object placed
against the vegetated field, in order: gate pairs, towns, the accent landmarks, the economy
mines, the other mines, shipyards, then dwellings, banks and visitables. Each zone draws its
total at the corpus rate, and the forced objects count inside it. A town may cover the
zone's entrance bands and spill onto vegetation beyond it. Every player town is protected
from then on, so no later object guards its entrance or walls in its start."""

from __future__ import annotations

from collections.abc import Sequence
from typing import final, override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Identity, MapState, PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.core.placement.guards import inflate_gap
from vcmi_mapgen.core.placement.site import (
    HOME_FOOTING,
    Footing,
    LevelField,
    PlacedZone,
    SiteIndex,
    SiteZone,
    ZoneSite,
)
from vcmi_mapgen.core.placement.start_room import StartRoomRule
from vcmi_mapgen.core.planning import zone_plan as ZPL
from vcmi_mapgen.core.planning.content import ContentPlan
from vcmi_mapgen.core.planning.pricing import effort_with
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.reading.paint import Accent
from vcmi_mapgen.core.steps.gameplay.draw import (
    TOWN_MIN_AREA,
    TOWN_SLOTS,
    DrawSpec,
    ZoneDraw,
    ZoneDrawer,
)
from vcmi_mapgen.core.steps.gameplay.economy import BASIC_MINE_RES, Ledger, tie_dwellings
from vcmi_mapgen.core.steps.gameplay.fallback import smaller
from vcmi_mapgen.core.steps.gameplay.gate_pairs import place_gate_pairs
from vcmi_mapgen.core.steps.gameplay.landmark import (
    LANDMARK_FLOOR,
    dragon_order,
    place_dragon,
    place_landmarks,
)
from vcmi_mapgen.core.steps.gameplay.result import GameplayResult, GateResult, TownsIndex
from vcmi_mapgen.core.steps.gameplay.shipyards import Shore, place_shipyards
from vcmi_mapgen.core.steps.terrain_gen.result import Accents, Segmentation, TerrainGrids
from vcmi_mapgen.core.steps.vegetation.result import VegetationResult

NO_TILES: frozenset[Tile] = frozenset()


def place_town(
    site: ZoneSite, draw: ZoneDraw, player: bool, footing: Footing | None = None
) -> PlacedObject | None:
    """Place a zone's town: a player town pulls toward the zone centre, a neutral one follows
    the corpus intensity. ``footing`` replaces the town's default footing."""
    if draw.town is None:
        return None
    centres = site.centroid_order(draw.town) if player else site.intensity_order(Purpose.TOWN)
    town = site.place(Purpose.TOWN, draw.town, centres, footing)
    if town is None:
        if player:
            print(
                f"  WARNING: player zone {site.zid} (level {site.lf.level}) "
                + "could not fit its town"
            )
        else:
            print(f"  zone {site.zid}: no spot for TOWN {draw.town.kind}")
    return town


def place_mines(site: ZoneSite, draw: ZoneDraw, ledger: Ledger, placed_res: set[str]) -> None:
    """Place a zone's mines: the economy pair nearest the town, the rest by intensity. A basic
    mine that finds no spot goes back to the ledger's missing set."""
    for i, ident in enumerate(draw.mines):
        centre = site.town_center
        centres = (
            site.nearest_order(*centre)
            if centre is not None and i < 2
            else site.intensity_order(Purpose.MINE)
        )
        res = str(ident.subtype)
        if site.place(Purpose.MINE, ident, centres) is not None:
            placed_res.add(res)
            continue
        print(f"  zone {site.zid}: no spot for MINE {ident.kind}")
        if res in BASIC_MINE_RES and res not in placed_res:
            ledger.missing.add(res)


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


def place_attractions(site: ZoneSite, draw: ZoneDraw) -> None:
    """Place a zone's dwellings, banks and visitables. A shipyard or a moved player town the
    zone received already used slots of the drawn total, so as many attractions drop from the
    end. An attraction that finds no spot falls back to a smaller object of its purpose, the
    largest shape first."""
    items = draw.attractions
    if site.spent:
        items = items[: max(0, len(items) - site.spent)]
    for purpose, ident in items:
        order = site.intensity_order(purpose)
        if site.place(purpose, ident, order) is not None:
            continue
        smaller_ids = smaller(site, draw.pools.get(purpose, []), ident)
        if not any(site.place(purpose, alt, order) is not None for alt in smaller_ids):
            print(f"  zone {site.zid}: no spot for {purpose} {ident.kind}")


@final
class GameplayStep(PipelineStep):
    """Place every gameplay object once vegetation has grown.

    Config:
        priors      The corpus priors; the step reads the gameplay statistics and the gate
                    estimator.
        seed        RNG seed.
        players     Number of player zones to designate (0 = neutral map).
        size        Map side length in tiles (square).
        subterrain  Whether a second underground level is active.

    inject(ctx): ``ZonePlan`` (each zone's plan, the player zones and the sea objects),
    ``VegetationResult`` (each zone's open and walkable tiles), ``TerrainGrids`` (the tunnel
    protect set), ``Segmentation`` (the surface zones), and the ``ContentPlan`` when present:
    a planned home's town may lay its overlay outside the zone, and each zone's total scales
    by its planned reward. The ``Accents`` when present: each accent patch of
    ``LANDMARK_FLOOR`` tiles or more takes a landmark right after the towns, one slot of its
    zone's total. The patch the homes reach last takes a dragon dwelling behind a level-7
    guard instead. The step publishes the player zones the zone plan picked, then commits the
    sea objects the zone plan drew. Gates stay off each player town's kept room. Gates may
    stand on an underground tunnel. No other object's footprint may, and none may strand one.
    A player town that finds no spot in its zone moves to the largest zone with room for it.

    Produces: appends the objects to ``map_state.objs``, sets ``map_state.gate_blk`` and
    ``map_state.player_towns``. Into ctx: ``TownsIndex``, ``GateResult`` and
    ``GameplayResult``.
    """

    def __init__(
        self,
        priors: Priors,
        seed: int = 3,
        players: int = 0,
        size: int = 72,
        subterrain: bool = False,
    ) -> None:
        self.priors = priors
        self.seed = seed
        self.players = players
        self.size = size
        self.subterrain = subterrain
        self.objs: list[PlacedObject] = []
        self._ctx = ProviderRegistry()
        self._plan = ZPL.ZonePlan({}, ())
        self._veg = VegetationResult()
        self._grids: dict[int, list[list[Terrain]]] = {}
        self._segmentation = Segmentation({}, {})
        self._player_zids: list[tuple[int, int]] = []
        self._tunnels: frozenset[Tile] = NO_TILES
        self._placed_res: set[str] = set()
        self._starts: dict[int, StartRoomRule] = {}
        self._content = ContentPlan()
        self._accents = Accents()

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx
        self._plan = ctx.require(ZPL.ZonePlan)
        self._veg = ctx.require(VegetationResult)
        self._tunnels = ctx.require(TerrainGrids).tunnel_protect
        self._segmentation = ctx.require(Segmentation)
        self._content = ctx.get(ContentPlan, ContentPlan())
        self._accents = ctx.get(Accents, Accents())

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
        ledger = Ledger(set(BASIC_MINE_RES), len(self._player_zids), 0)
        draws = self._place_towns(catalog, indexes, ledger)
        if 0 in indexes:
            self._place_shipyards(indexes[0], map_state, catalog)
        dragon = self._place_dragon(catalog, indexes, map_state)
        for (level, zid), draw in sorted(draws.items()):
            site = indexes[level].sites[zid]
            patches = self._accents.levels.get(level, ())
            skip = dragon[1] if dragon is not None and dragon[0] == level else None
            site.spent += place_landmarks(site, patches, self.seed, skip)
            place_mines(site, draw, ledger, self._placed_res)
        if 0 in indexes:
            indexes[0].lf.avoid = NO_TILES
        for (level, zid), draw in sorted(draws.items()):
            place_attractions(indexes[level].sites[zid], draw)
        self._finish(catalog, indexes, map_state)
        if ledger.missing:
            print(f"  WARNING: mine coverage incomplete — missing {sorted(ledger.missing)}")
        self._ctx.provide(gates)

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
        if 1 in indexes:
            for site in indexes[1].sites.values():
                site.reserved |= self._tunnels & site.ts
        return gates

    def _place_towns(
        self, catalog: Catalog, indexes: dict[int, SiteIndex], ledger: Ledger
    ) -> dict[tuple[int, int], ZoneDraw]:
        draws: dict[tuple[int, int], ZoneDraw] = {}
        for level, idx in sorted(indexes.items()):
            for zid, site in sorted(idx.sites.items()):
                draws[level, zid] = self._draw(site, ledger)
                player = (level, zid) in self._player_zids
                footing = HOME_FOOTING if (level, zid) in self._content.homes else None
                town = place_town(site, draws[level, zid], player, footing)
                if player and town is not None:
                    self._starts[level].protect(town)
        self._move_player_towns(catalog, indexes)
        return draws

    def _move_player_towns(self, catalog: Catalog, indexes: dict[int, SiteIndex]) -> None:
        sites = [s for _l, idx in sorted(indexes.items()) for _z, s in sorted(idx.sites.items())]
        need = self.players - sum(1 for s in sites if s.town_center is not None)
        ident = catalog.random_town()
        for site in _town_hosts(sites):
            if need <= 0:
                return
            town = site.place(Purpose.TOWN, ident, _town_order(site, ident))
            if town is not None:
                self._starts[site.lf.level].protect(town)
                site.spent += TOWN_SLOTS
                need -= 1
                print(f"  player town moved to zone {site.zid} (level {site.lf.level})")
        if need > 0:
            print(f"  WARNING: {need} player town(s) found no zone with room")

    def _place_dragon(
        self, catalog: Catalog, indexes: dict[int, SiteIndex], map_state: MapState
    ) -> tuple[int, Accent] | None:
        if not any(p.size >= LANDMARK_FLOOR for ps in self._accents.levels.values() for p in ps):
            return None
        objs = [o for idx in indexes.values() for site in idx.sites.values() for o in site.objs]
        towns: dict[tuple[int, int], list[PlacedObject]] = {}
        for level, idx in sorted(indexes.items()):
            for zid, site in sorted(idx.sites.items()):
                zone_towns = [o for o in site.objs if o.purpose == Purpose.TOWN]
                if zone_towns:
                    towns[level, zid] = zone_towns
        view = MapState(
            size=map_state.size,
            terrain=map_state.terrain,
            gate_blk=map_state.gate_blk,
            objs=[*map_state.objs, *objs],
            player_towns=self._player_towns(towns),
        )
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
        lf = LevelField.build(
            level,
            self._grids[level],
            [o for o in map_state.objs if o.level == level],
            rules=(self._starts[level],),
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

    def _draw(self, site: ZoneSite, ledger: Ledger) -> ZoneDraw:
        level = site.lf.level
        spec = DrawSpec(
            zid=site.zid,
            terrain=site.zone.terrain,
            area=len(site.zone.ts),
            player=(level, site.zid) in self._player_zids,
            gates=site.gates,
            has_water=any(Terrain.WATER in row for row in self._grids[level]),
            has_subterrain=self.subterrain,
            scale=self._content.scale(level, site.zid),
        )
        return ZoneDrawer(site.catalog, spec, site.st, ledger, self.seed + level).draw()

    def _place_shipyards(self, idx: SiteIndex, map_state: MapState, catalog: Catalog) -> None:
        objs = [o for o in map_state.objs if o.level == 0 and o.purpose]
        objs += [o for site in idx.sites.values() for o in site.objs]
        shore = Shore(self._grids[0], self._segmentation.zones[0], objs)
        avoid, idx.lf.avoid = idx.lf.avoid, NO_TILES
        n = place_shipyards(idx, shore, self.seed, catalog)
        idx.lf.avoid = avoid
        print(f"  L0 seaport guarantee: {n} shipyard(s) added")

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
                tie_dwellings(catalog, site.objs)
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
        self._ctx.provide(GameplayResult(zones, landings, town_of_zone))

    def _player_towns(self, towns: dict[tuple[int, int], list[PlacedObject]]) -> list[PlacedObject]:
        out = [towns[k][0] for k in self._player_zids if k in towns]
        if not self.players:
            return out
        spare: Sequence[PlacedObject] = [
            t for zone_towns in towns.values() for t in zone_towns if t not in out
        ]
        out += spare[: max(0, self.players - len(out))]
        return out[: self.players]

"""GameplayStep: the player-zone pick, the sea objects, then every gameplay object placed
against the vegetated field, in order: gate pairs, towns, the economy mines, the other
mines, shipyards, then dwellings, banks and visitables. Each zone draws its total at the
corpus rate, and the forced objects count inside it."""

from __future__ import annotations

from collections.abc import Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from typing import final, override

from vcmi_mapgen.core.model import Identity, MapState, PlacedObject, Tile
from vcmi_mapgen.core.pipeline import (
    LevelWorkspace,
    PipelineStep,
    PlacementWorkspace,
    ProviderRegistry,
    ZoneWorkspace,
)
from vcmi_mapgen.core.steps.gameplay.draw import TOWN_SLOTS, DrawSpec, ZoneDraw, ZoneDrawer
from vcmi_mapgen.core.steps.gameplay.gate_pairs import GateResult, place_gate_pairs
from vcmi_mapgen.core.steps.gameplay.mines import (
    BASIC_MINE_RES,
    RND_TOWN,
    TOWN_MIN_AREA,
    Ledger,
    tie_dwellings,
)
from vcmi_mapgen.core.steps.gameplay.shipyards import Shore, place_shipyards
from vcmi_mapgen.core.steps.gameplay.site import LevelField, SiteIndex, ZoneSite
from vcmi_mapgen.core.steps.gate.gates import footprint_cells, inflate_gap
from vcmi_mapgen.core.steps.terrain_gen.step import TerrainGrids
from vcmi_mapgen.core.steps.zone_plan import seaport_cells
from vcmi_mapgen.validate import TerrainGate
from vcmi_mapgen.vcmi.catalog import objects as ON
from vcmi_mapgen.vcmi.catalog.adapter import Ontology

NO_TILES: frozenset[Tile] = frozenset()
WATER = 8
LAND = 2


@dataclass
class TownsIndex:
    """Which zones host a player town: PortalStep's, LootStep's, BorderStep's and the CLI's
    input. A run stopped before GameplayStep reads the empty default."""

    player_zids: list[tuple[int, int]] = field(default_factory=list)


def place_town(site: ZoneSite, draw: ZoneDraw, player: bool) -> None:
    """Place a zone's town: a player town pulls toward the zone centre, a neutral one follows
    the corpus intensity."""
    if draw.town is not None:
        centres = site.centroid_order(draw.town) if player else site.intensity_order("TOWN")
        if site.place("TOWN", draw.town, centres) is None:
            if player:
                print(
                    f"  WARNING: player zone {site.zid} (level {site.lf.level}) "
                    + "could not fit its town"
                )
            else:
                print(f"  zone {site.zid}: no spot for TOWN {draw.town.animation}")


def place_mines(site: ZoneSite, draw: ZoneDraw, ledger: Ledger, placed_res: set[str]) -> None:
    """Place a zone's mines: the economy pair nearest the town, the rest by intensity. A basic
    mine that finds no spot goes back to the ledger's missing set."""
    for i, ident in enumerate(draw.mines):
        centre = site.town_center
        centres = (
            site.nearest_order(*centre)
            if centre is not None and i < 2
            else site.intensity_order("MINE")
        )
        res = str(ident.subtype)
        if site.place("MINE", ident, centres) is not None:
            placed_res.add(res)
            continue
        print(f"  zone {site.zid}: no spot for MINE {ident.animation}")
        if res in BASIC_MINE_RES and res not in placed_res:
            ledger.missing.add(res)


def _town_hosts(sites: Sequence[ZoneSite]) -> list[ZoneSite]:
    free = [s for s in sites if s.town_center is None and len(s.zw.ts_full) >= TOWN_MIN_AREA]
    shared = [
        s for s in sites if s.town_center is not None and len(s.zw.ts_full) >= 4 * TOWN_MIN_AREA
    ]
    return [
        *sorted(free, key=lambda s: -len(s.zw.ts_full)),
        *sorted(shared, key=lambda s: -len(s.zw.ts_full)),
    ]


def _town_order(site: ZoneSite, ident: Identity) -> list[Tile]:
    if site.town_center is None:
        return site.centroid_order(ident)
    cx, cy = site.town_center
    return sorted(site.ts, key=lambda t: (-((t[0] - cx) ** 2 + (t[1] - cy) ** 2), t))


def _footprint_size(ident: Identity) -> int:
    return len(footprint_cells(ident, 0, 0)[0])


def _smaller(site: ZoneSite, pool: Sequence[Identity], ident: Identity) -> list[Identity]:
    size = _footprint_size(ident)
    by_mask: dict[tuple[str, ...], list[Identity]] = {}
    for cand in sorted(pool, key=lambda i: i.animation):
        if _footprint_size(cand) < size:
            by_mask.setdefault(cand.mask, []).append(cand)
    shapes = sorted(by_mask.values(), key=lambda ids: (-_footprint_size(ids[0]), ids[0].mask))
    return [site.rng.choice(ids) for ids in shapes]


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
        smaller = _smaller(site, draw.pools.get(purpose, []), ident)
        if not any(site.place(purpose, alt, order) is not None for alt in smaller):
            print(f"  zone {site.zid}: no spot for {purpose} {ident.animation}")


def place_open_zone(
    ts: AbstractSet[Tile],
    terrain: str,
    seed: int,
    player: bool = False,
    ledger: Ledger | None = None,
) -> ZoneWorkspace:
    """Draw and place one zone of open land with no vegetation and a one-tile web at its
    top-left corner, outside any pipeline. Returns its workspace after write-back."""
    w = max(x for x, _y in ts) + 1
    h = max(y for _x, y in ts) + 1
    zw = ZoneWorkspace(
        terrain=terrain,
        ts=frozenset(ts),
        ts_full=frozenset(ts),
        prot=frozenset({min(ts)}),
        open_set=frozenset(ts),
        passable=frozenset(ts),
    )
    lf = LevelField.build(0, [[LAND] * w for _ in range(h)], [], lambda _o: True)
    site = ZoneSite(1, zw, lf, seed)
    ledger = ledger or Ledger(set(BASIC_MINE_RES), 1, 0)
    spec = DrawSpec(1, terrain, len(ts), player=player)
    draw = ZoneDrawer(spec, site.st, ledger, seed).draw()
    place_town(site, draw, player)
    place_mines(site, draw, ledger, set())
    place_attractions(site, draw)
    site.write_back()
    tie_dwellings(zw.gobjs)
    return zw


@final
class GameplayStep(PipelineStep):
    """Place every gameplay object once vegetation has grown.

    Config:
        seed        RNG seed.
        players     Number of player zones to designate (0 = neutral map).
        size        Map side length in tiles (square).
        subterrain  Whether a second underground level is active.

    inject(ctx): ``PlacementWorkspace`` (each zone's post-vegetation field), ``TerrainGrids``
    (the grids and the tunnel protect set). The step publishes the player zones the zone plan
    picked, then commits the sea objects the zone plan drew. Gates stay off each player town's
    kept room. Gates may stand on an underground tunnel. No other object's footprint may,
    and none may strand one. A player town that finds no spot in its zone moves to the
    largest zone with room for it.

    Produces: appends the objects to ``map_state.objs``, sets ``map_state.gate_blk`` and
    ``map_state.player_towns``, folds the objects into each ``ZoneWorkspace`` and sets each
    ``LevelWorkspace``'s ``town_of_zone``, ``seaport_blk`` and ``seaport_appr``. Into ctx:
    ``TownsIndex`` and ``GateResult``.
    """

    def __init__(
        self, seed: int = 3, players: int = 0, size: int = 72, subterrain: bool = False
    ) -> None:
        self.seed = seed
        self.players = players
        self.size = size
        self.subterrain = subterrain
        self.objs: list[PlacedObject] = []
        self._ctx = ProviderRegistry()
        self._workspace = PlacementWorkspace()
        self._grids: dict[int, list[list[int]]] = {}
        self._player_zids: list[tuple[int, int]] = []
        self._tunnels: frozenset[Tile] = NO_TILES
        self._placed_res: set[str] = set()

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx
        self._workspace = ctx.get_or_create(PlacementWorkspace, PlacementWorkspace)
        terrain = ctx.require(TerrainGrids)
        self._grids = terrain.grids
        self._tunnels = terrain.tunnel_protect

    @override
    def run(self, ontology: Ontology, map_state: MapState) -> None:
        gate = TerrainGate(ontology)
        self._pick_player_zones()
        for _level, lw in sorted(self._workspace.levels.items()):
            map_state.add_objs(list(lw.sea), gate)
        indexes = {
            level: self._index(level, lw, map_state, gate)
            for level, lw in sorted(self._workspace.levels.items())
        }
        gates = self._place_gates(indexes, map_state)
        ledger = Ledger(set(BASIC_MINE_RES), len(self._player_zids), 0)
        draws = self._place_towns(indexes, ledger)
        for (level, zid), draw in sorted(draws.items()):
            place_mines(indexes[level].sites[zid], draw, ledger, self._placed_res)
        if 0 in indexes:
            indexes[0].lf.avoid = NO_TILES
            self._place_shipyards(indexes[0], map_state, ontology)
        for (level, zid), draw in sorted(draws.items()):
            place_attractions(indexes[level].sites[zid], draw)
        self._finish(indexes, map_state, gate)
        if ledger.missing:
            print(f"  WARNING: mine coverage incomplete — missing {sorted(ledger.missing)}")
        self._ctx.provide(gates)

    def _pick_player_zones(self) -> None:
        self._player_zids = list(self._workspace.player_zids)
        self._ctx.provide(TownsIndex(player_zids=self._player_zids))

    def _place_gates(self, indexes: dict[int, SiteIndex], map_state: MapState) -> GateResult:
        landings = self._landings() if 0 in indexes else set[Tile]()
        for level, idx in indexes.items():
            rooms = (zw.town_room for zw in self._workspace.levels[level].zones.values())
            idx.lf.avoid = frozenset[Tile]().union(*rooms) | (landings if level == 0 else NO_TILES)
        gates = GateResult()
        if self.subterrain and 0 in indexes and 1 in indexes:
            gates = place_gate_pairs(indexes[0], indexes[1], map_state.size, self.seed)
        for level, idx in indexes.items():
            idx.lf.avoid = landings if level == 0 else NO_TILES
        map_state.gate_blk = gates.gate_blk
        if 1 in indexes:
            for site in indexes[1].sites.values():
                site.reserved |= self._tunnels & site.ts
        return gates

    def _place_towns(
        self, indexes: dict[int, SiteIndex], ledger: Ledger
    ) -> dict[tuple[int, int], ZoneDraw]:
        draws: dict[tuple[int, int], ZoneDraw] = {}
        for level, idx in sorted(indexes.items()):
            for zid, site in sorted(idx.sites.items()):
                draws[level, zid] = self._draw(site, ledger)
                place_town(site, draws[level, zid], (level, zid) in self._player_zids)
        self._move_player_towns(indexes)
        return draws

    def _move_player_towns(self, indexes: dict[int, SiteIndex]) -> None:
        sites = [s for _l, idx in sorted(indexes.items()) for _z, s in sorted(idx.sites.items())]
        need = self.players - sum(1 for s in sites if s.town_center is not None)
        ident = ON.identity_of(RND_TOWN)
        for site in _town_hosts(sites):
            if need <= 0:
                return
            if site.place("TOWN", ident, _town_order(site, ident)) is not None:
                site.spent += TOWN_SLOTS
                need -= 1
                print(f"  player town moved to zone {site.zid} (level {site.lf.level})")
        if need > 0:
            print(f"  WARNING: {need} player town(s) found no zone with room")

    def _landings(self) -> set[Tile]:
        lw = self._workspace.levels[0]
        landing: set[Tile] = set()
        inflate_gap(landing, lw.seaport_blk | lw.seaport_appr)
        return landing

    def _index(
        self, level: int, lw: LevelWorkspace, map_state: MapState, gate: TerrainGate
    ) -> SiteIndex:
        lf = LevelField.build(
            level,
            self._grids[level],
            [o for o in map_state.objs if o.level == level],
            lambda o: not gate.check(o, map_state.cells),
        )
        idx = SiteIndex(lf)
        for zid, zw in sorted(lw.zones.items()):
            idx.sites[zid] = ZoneSite(zid, zw, lf, self.seed)
            idx.zone_of.update(dict.fromkeys(zw.ts, zid))
        return idx

    def _draw(self, site: ZoneSite, ledger: Ledger) -> ZoneDraw:
        level = site.lf.level
        spec = DrawSpec(
            zid=site.zid,
            terrain=site.zw.terrain,
            area=len(site.zw.ts_full),
            player=(level, site.zid) in self._player_zids,
            gates=site.gates,
            has_water=any(WATER in row for row in self._grids[level]),
            has_subterrain=self.subterrain,
        )
        return ZoneDrawer(spec, site.st, ledger, self.seed + level).draw()

    def _place_shipyards(self, idx: SiteIndex, map_state: MapState, ontology: Ontology) -> None:
        objs = [o for o in map_state.objs if o.level == 0 and o.purpose]
        objs += [o for site in idx.sites.values() for o in site.objs]
        shore = Shore(self._grids[0], map_state.zones[0], objs)
        n = place_shipyards(idx, shore, self.seed, ontology)
        print(f"  L0 seaport guarantee: {n} shipyard(s) added")

    def _finish(
        self, indexes: dict[int, SiteIndex], map_state: MapState, gate: TerrainGate
    ) -> None:
        towns: dict[tuple[int, int], list[PlacedObject]] = {}
        for level, idx in sorted(indexes.items()):
            lw = self._workspace.levels[level]
            for zid, site in sorted(idx.sites.items()):
                site.write_back()
                tie_dwellings(site.zw.gobjs)
                self.objs.extend(site.objs)
                zone_towns = [o for o in site.objs if o.purpose == "TOWN"]
                if zone_towns:
                    lw.town_of_zone[zid] = zone_towns[0]
                    towns[level, zid] = zone_towns
            blk, appr = seaport_cells(o for o in [*map_state.objs, *self.objs] if o.level == level)
            lw.seaport_blk = frozenset(blk)
            lw.seaport_appr = frozenset(appr)
        map_state.add_objs(self.objs, gate)
        map_state.player_towns = self._player_towns(towns)

    def _player_towns(self, towns: dict[tuple[int, int], list[PlacedObject]]) -> list[PlacedObject]:
        out = [towns[k][0] for k in self._player_zids if k in towns]
        if not self.players:
            return out
        spare: Sequence[PlacedObject] = [
            t for zone_towns in towns.values() for t in zone_towns if t not in out
        ]
        out += spare[: max(0, self.players - len(out))]
        return out[: self.players]

"""TownsStep — towns, mines, water bodies, seaports, and the zone-level ledger, before
vegetation."""

from __future__ import annotations

import collections
from collections.abc import Collection, Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from typing import final, override

from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.kit.geometry import NB8, edge_dist
from vcmi_mapgen.kit.terrain_lookup import TNAME
from vcmi_mapgen.kit.topology import geodesic_path, plan_entrances
from vcmi_mapgen.models import Entrance, MapState, PlacedObject, Tile, Zone
from vcmi_mapgen.ontology import Ontology
from vcmi_mapgen.pipeline import (
    LevelWorkspace,
    PipelineStep,
    PlacementWorkspace,
    ProviderRegistry,
    ZoneWorkspace,
)
from vcmi_mapgen.steps.gameplay import mines as MN
from vcmi_mapgen.steps.gameplay import water as WT
from vcmi_mapgen.steps.gate.step import GateResult
from vcmi_mapgen.steps.terrain_gen.step import TerrainGrids
from vcmi_mapgen.steps.vegetation import sample as PP  # protected_web
from vcmi_mapgen.validate import TerrainGate

NO_TILES: frozenset[Tile] = frozenset()
NO_APPROACHES: tuple[Tile, ...] = ()

MIN_AREA = 25  # vegetate even smallish zones (the stats floor stays 60 in vegetation)


@dataclass
class TownsIndex:
    """Which zones host a player town — PortalStep's (`_find_start`), LootStep's and the
    CLI's input. Read via ``ctx.require(TownsIndex)`` (TownsStep always runs when
    generate does; a stopped-early --stop-after run reads it with ``ctx.get(...,
    TownsIndex())`` instead)."""

    player_zids: list[tuple[int, int]] = field(default_factory=list)


def _rim8(zones: Mapping[int, Zone]) -> set[Tile]:
    """The 8-connected inter-zone rim: every tile with an 8-neighbour in another zone
    (both sides of every border). Diagonal contact counts — corner-cutting is a legal
    hero move in H3, so a diagonal-only touch leaks exactly like a shared edge."""
    owner: dict[Tile, int] = {}
    for zid, z in zones.items():
        for t in z.tiles_set:
            owner[t] = zid
    return {
        t
        for t, zid in owner.items()
        if any(owner.get((t[0] + dx, t[1] + dy), zid) != zid for dx, dy in NB8)
    }


type LevelResult = tuple[
    list[PlacedObject],
    dict[int, ZoneWorkspace],
    dict[int, list[Entrance]],
    bool,
    dict[int, PlacedObject],
    frozenset[Tile],
    frozenset[Tile],
    frozenset[Tile],
]


@dataclass(frozen=True, slots=True)
class _LevelInput:
    level: int
    W: int
    H: int
    grid: Sequence[Sequence[int]]
    zones: Mapping[int, Zone]
    player_zids: Collection[int]
    ledger: MN.Ledger
    gstats: Mapping[str, MN.TerrainStats]
    seed: int
    has_subterrain: bool
    gate_occ: AbstractSet[Tile] = NO_TILES
    gate_blk: AbstractSet[Tile] = NO_TILES
    gate_appr: Collection[Tile] = NO_APPROACHES
    tunnel_protect: frozenset[Tile] = NO_TILES
    gate_objs: Sequence[PlacedObject] = ()


def _run_level_gameplay(lv: _LevelInput, ontology: Ontology) -> LevelResult:
    """The pre-vegetation half of the map-generation pass: water-body population (surface
    only), per-zone ``mines.place_zone`` + protected web, and the seaport guarantee.
    ``TownsStep.run()`` is its only caller.

    Returns (objs, zone_cache, entrance_plan, has_water, town_of_zone, ridge, seaport_blk,
    seaport_appr): ``zone_cache`` is ``{zid: {...}}`` with the same keys `_run_level`'s
    Pass 2 (vegetation, gated and treasure) already expects."""
    return _LevelGameplay(lv, ontology).run()


def _seaport_cells(objs: Iterable[PlacedObject]) -> tuple[set[Tile], set[Tile]]:
    seaport_blk: set[Tile] = set()
    seaport_appr: set[Tile] = set()
    for _so in objs:
        if _so.type == "shipyard":
            for _scx, _scy, _sblk in OR.mask_cells(_so.mask, _so.x, _so.y):
                if _sblk:
                    seaport_blk.add((_scx, _scy))
            seaport_appr.add((_so.x - 1, _so.y + 1))
    return seaport_blk, seaport_appr


def _connect_seaports(
    seaport_appr: Iterable[Tile],
    seaport_blk: AbstractSet[Tile],
    zone_cache: Mapping[int, ZoneWorkspace],
) -> None:
    for appr in seaport_appr:
        for zw in zone_cache.values():
            if appr not in zw.ts_full or appr in zw.prot:
                continue
            free = zw.ts - zw.gblocked - seaport_blk
            goals = sorted(
                zw.prot & free, key=lambda t: (abs(t[0] - appr[0]) + abs(t[1] - appr[1]), t)
            )
            path = next((p for g in goals if (p := geodesic_path(appr, g, free))), list[Tile]())
            zw.prot = zw.prot | frozenset(path)


@final
class _LevelGameplay:
    def __init__(self, lv: _LevelInput, ontology: Ontology) -> None:
        self.lv = lv
        self.ontology = ontology
        self.objs: list[PlacedObject] = []
        self.town_of_zone: dict[int, PlacedObject] = {}

        # map-level isolation plan: 1-2 aligned narrow crossings per adjacent zone pair,
        # computed ONCE over all zones so both sides agree where the entrances are. Everything
        # downstream keys off it: gameplay keeps footprints off the bands and guards the reps,
        # the protected web keeps only the bands vegetation-free (not the legacy wide corpus-open
        # share of the front), and the vegetation sampler actively densifies the rest of the
        # border (`border=` bias) so zones read as isolated regions with a few real entrances.
        # `seal_zone_borders` below then closes whatever aligned holes the statistics left.
        self.entrance_plan = plan_entrances(lv.zones)
        self.ridge: set[Tile] = set()  # all rim tiles minus entrance bands
        self.rim_all = _rim8(lv.zones)  # 8-connected inter-zone rim, both sides

        self.has_water = False
        self.zone_cache: dict[int, ZoneWorkspace] = {}  # zid → per-zone data needed for pass 2

    def _populate_water(self, water: AbstractSet[Tile]) -> None:
        seen_w: set[Tile] = set()
        wi = 0
        for t0 in sorted(water):
            if t0 in seen_w:
                continue
            comp, q = {t0}, [t0]
            while q:
                x, y = q.pop()
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    n = (x + dx, y + dy)
                    if n in water and n not in comp:
                        comp.add(n)
                        q.append(n)
            seen_w |= comp
            if len(comp) >= MIN_AREA:
                wobjs = WT.place_water(comp, self.lv.zones, 1000 + wi, seed=self.lv.seed)
                self.objs.extend(wobjs)
                print(f"  sea  {wi:>3} water    {len(comp):>5} tiles: {len(wobjs):>3} sea objects")
            wi += 1

    def _coastal(self, ts: AbstractSet[Tile]) -> frozenset[Tile]:
        W, H, grid = self.lv.W, self.lv.H, self.lv.grid
        return frozenset(
            t
            for t in ts
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            if 0 <= t[0] + dx < W and 0 <= t[1] + dy < H and grid[t[1] + dy][t[0] + dx] == 8
        )

    def _record_town(self, zid: int, gobjs: Iterable[PlacedObject]) -> None:
        t = next((o for o in gobjs if o.purpose == "TOWN"), None)
        if t is not None:
            self.town_of_zone[zid] = t
        else:
            print(f"  WARNING: player zone {zid} (level {self.lv.level}) could not fit its town")

    def _zone_workspace(self, zid: int, z: Zone, terrain: str) -> ZoneWorkspace:
        lv = self.lv
        ts_full = set(z.tiles_set)
        ts = ts_full
        z_gate_occ = ts_full & lv.gate_occ
        z_gate_blk = ts_full & lv.gate_blk
        z_gate_appr = tuple(a for a in lv.gate_appr if a in ts_full)
        coastal = self._coastal(ts)

        # L3 gameplay first: rigid objects at spread nodes (corpus densities, ontology pools)
        # `avoid` keeps every footprint/approach off the corridor protect set — gameplay
        # runs before `protected_web`, so without this a town/mine/monster could wall off
        # a tunnel that vegetation-forbidding alone could never have touched.
        z_entr = self.entrance_plan.get(zid, [])
        plan = MN.place_zone(
            ts,
            lv.zones,
            zid,
            terrain,
            MN.ZoneOptions(
                seed=lv.seed,
                coastal=coastal,
                force_town=zid in lv.player_zids,
                ledger=lv.ledger,
                has_water=self.has_water,
                level=lv.level,
                has_subterrain=lv.has_subterrain,
                avoid=lv.tunnel_protect & ts,
                preoccupied=z_gate_occ,
                preblocked=z_gate_blk,
                preapproaches=z_gate_appr,
                entrances=z_entr,
            ),
        )
        self.objs.extend(plan.objs)
        if zid in lv.player_zids:
            self._record_town(zid, plan.objs)

        # protected walkable web: backbone + gates + gameplay approaches, routed around the
        # IMPASSABLE gameplay cells (approach tiles themselves are passable and stay nodes)
        edist = edge_dist(ts)
        zcx, zcy = z.centroid
        seedt = min(ts, key=lambda t: (t[0] - round(zcx)) ** 2 + (t[1] - round(zcy)) ** 2)
        # the zone's 8-connected rim: every tile with an 8-neighbour in ANOTHER zone
        # (diagonal corner-cutting is a legal hero move, so diagonal-only contact leaks
        # like a front tile). The web routes off it, scatter skips it, the sampler's
        # border bias targets it, and repair prices carving it at 400.
        ent_bands: set[Tile] = set[Tile]().union(*(b for _r, b, _o in z_entr)) if z_entr else set()
        rim8 = self.rim_all & ts
        self.ridge |= rim8 - ent_bands
        prot = PP.protected_web(
            PP.ZoneRef(ts, lv.zones, zid),
            edist,
            seedt,
            PP.WebOptions(
                extra_nodes=plan.approaches,
                avoid=plan.blocked,
                open_frac=lv.gstats[terrain].border_open_frac,
                entrances=z_entr,
                keep_off=rim8,
            ),
        )
        prot = prot | (lv.tunnel_protect & ts)
        return ZoneWorkspace(
            terrain=terrain,
            ts=frozenset(ts),
            ts_full=frozenset(ts_full),
            gobjs=plan.objs,
            occupied=frozenset(plan.occupied),
            gblocked=frozenset(plan.blocked),
            approaches=tuple(plan.approaches),
            entrances=z_entr,
            prot=frozenset(prot),
            rim8=frozenset(rim8),
            ent_bands=frozenset(ent_bands),
            planned=list(plan.planned),
        )

    def run(self) -> LevelResult:
        lv = self.lv
        water_tiles = {(x, y) for y in range(lv.H) for x in range(lv.W) if lv.grid[y][x] == 8}
        if lv.level == 0:
            # water is a segmentation BARRIER (never a zone) — populate its connected bodies
            # directly: flotsam / sea chests / buoys / boats / whirlpools / wrecks / sea guards
            water = water_tiles
            self.has_water = bool(water)
            self._populate_water(water)

        # ── Pass 1: L3 gameplay for all zones ─────────────────────────────────────
        # Seaports are placed after all gameplay objects are known (so conflict
        # detection is complete), but BEFORE vegetation so veg forbids their footprint.
        for zid, z in sorted(lv.zones.items()):
            terrain = TNAME.get(z.terrain_type)
            if terrain in (None, "water", "rock") or z.area < MIN_AREA:
                continue
            self.zone_cache[zid] = self._zone_workspace(zid, z, terrain)

        # ── Seaport placement: after all gameplay objects, before vegetation ────────
        # Seaports are treated as gameplay objects: they block vegetation, their
        # approach tile is added to targets, and their footprint is excluded from
        # scatter open sets.  Placed here so the veg pass below can forbid their cells.
        if lv.level == 0:
            ship_objs = WT.ensure_water_seaports(
                WT.SeaMap(lv.W, lv.H, lv.grid, lv.zones),
                [*lv.gate_objs, *self.objs],
                lv.seed,
                self.ontology,
            )
            if ship_objs:
                self.objs.extend(ship_objs)
                print(f"  L{lv.level} seaport guarantee: {len(ship_objs)} shipyard(s) added")

        # Seaport blocking cells + approach tile — exclude from vegetation in pass 2.
        # The approach tile (one tile south of the X cell) must stay walkable so a
        # hero can board the ship.
        seaport_blk, seaport_appr = _seaport_cells(self.objs)

        _connect_seaports(seaport_appr, seaport_blk, self.zone_cache)
        return (
            self.objs,
            self.zone_cache,
            self.entrance_plan,
            self.has_water,
            self.town_of_zone,
            frozenset(self.ridge),
            frozenset(seaport_blk),
            frozenset(seaport_appr),
        )


class TownsStep(PipelineStep):
    """Place towns, mines with their guards and seals, water bodies and seaports per zone,
    before vegetation. The zone's dwellings, banks and visitables get their spots planned
    here too, recorded as ``ZoneWorkspace.planned``: GameplayStep emits them after
    vegetation.

    Config:
        seed        RNG seed.
        players     Number of player zones to designate (0 = neutral map).
        size        Map side length in tiles (square).
        subterrain  Whether a second underground level is active.

    Reads ``map_state.zones`` (SegmentStep) and ``map_state.gate_blk`` (GateStep, empty
    when there is no GateStep) directly in run(). inject(ctx): ``TerrainGrids``
    (TerrainStep's output — grids/tunnel_protect); ``GateResult`` (GateStep's output,
    defaulting to empty when there is no GateStep).

    Produces: ``objs``, ``player_towns`` — written directly onto MapState (all levels,
    underground tagged ``l=1``). Into ctx: ``TownsIndex`` (player_zids), the
    folded-in ``PlacementWorkspace`` (created here via ``get_or_create`` — the first of
    the four steps that share it), and ``self.workspace.levels[level]`` (a
    ``LevelWorkspace`` with a ``ZoneWorkspace`` per zone, ``ridge``, and
    ``town_of_zone`` for BorderStep — ``guard_tiles``/``seal_avoid``/``hard_avoid`` come
    from later steps' own border-seal pass, not from here). ``ledger`` is purely
    internal bookkeeping across this step's own zones, never read by anything else, so
    it stays a local instance attribute, not a published value.
    """

    def __init__(
        self, seed: int = 3, players: int = 0, size: int = 72, subterrain: bool = False
    ) -> None:
        self.seed: int = seed
        self.players: int = players
        self.size: int = size
        self.subterrain: bool = subterrain
        self.objs: list[PlacedObject] = []
        self.player_zids: list[tuple[int, int]] = []
        self.player_towns: list[PlacedObject] = []
        self.ledger: MN.Ledger = MN.Ledger(missing=set(), towns=0, gold=0)
        self._ctx: ProviderRegistry | None = None
        self._grids: dict[int, list[list[int]]] = {}
        self._tunnel_protect: frozenset[Tile] = NO_TILES
        self._gate_objs: list[PlacedObject] = []
        self._gate_occ: dict[int, set[Tile]] = {}
        self._gate_appr: dict[int, list[Tile]] = {}

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx
        terrain = ctx.require(TerrainGrids)
        self._grids = terrain.grids
        self._tunnel_protect = terrain.tunnel_protect
        gate = ctx.get(GateResult, GateResult())
        self._gate_objs = gate.gate_objs
        self._gate_occ = gate.gate_occ
        self._gate_appr = gate.gate_appr

    @override
    def run(self, ontology: Ontology, map_state: MapState) -> None:
        W = H = self.size
        zones_by_level = map_state.zones
        gate_blk_by_level = map_state.gate_blk

        player_zids = MN.select_player_zones(zones_by_level, self.players)
        if self.players and len(player_zids) < self.players:
            print(
                f"  WARNING: only {len(player_zids)} zones can host a player town "
                + f"(requested {self.players})"
            )

        zids_by_level: collections.defaultdict[int, set[int]] = collections.defaultdict(set)
        for lvl, zid in player_zids:
            zids_by_level[lvl].add(zid)

        ledger = MN.Ledger(
            missing=set(MN.BASIC_MINE_RES),
            towns=len(player_zids),
            gold=0,
        )

        assert self._ctx is not None
        workspace = self._ctx.get_or_create(PlacementWorkspace, PlacementWorkspace)

        all_town_of_zone: dict[int, dict[int, PlacedObject]] = {}
        all_ridge: dict[int, frozenset[Tile]] = {}
        all_objs: list[PlacedObject] = []

        for level in sorted(self._grids):
            grid = self._grids[level]
            zones = zones_by_level[level]
            gstats = MN.mine_gameplay(level=level)

            gate_occ = self._gate_occ.get(level, NO_TILES)
            gate_blk = gate_blk_by_level.get(level, NO_TILES)
            gate_appr = self._gate_appr.get(level, NO_APPROACHES)
            tunnel_protect = self._tunnel_protect if level == 1 else NO_TILES
            level_gate_objs = [o for o in self._gate_objs if o.level == level]

            (
                objs,
                zone_workspaces,
                entrance_plan,
                _has_water,
                town_of_zone,
                ridge,
                seaport_blk,
                seaport_appr,
            ) = _run_level_gameplay(
                _LevelInput(
                    level,
                    W,
                    H,
                    grid,
                    zones,
                    zids_by_level[level],
                    ledger,
                    gstats,
                    self.seed,
                    self.subterrain,
                    gate_occ=gate_occ,
                    gate_blk=gate_blk,
                    gate_appr=gate_appr,
                    tunnel_protect=tunnel_protect,
                    gate_objs=level_gate_objs,
                ),
                ontology,
            )

            objs.extend(level_gate_objs)

            # retag underground objects so downstream steps can partition by level
            if level == 1:
                for o in objs:
                    o.level = 1

            all_objs.extend(objs)
            all_town_of_zone[level] = town_of_zone
            all_ridge[level] = ridge

            workspace.levels[level] = LevelWorkspace(
                zones=zone_workspaces,
                entrance_plan=entrance_plan,
                ridge=ridge,
                seaport_blk=seaport_blk,
                seaport_appr=seaport_appr,
                town_of_zone=town_of_zone,
            )

        self.objs = all_objs
        self.player_zids = player_zids
        self.ledger = ledger

        # resolve player towns from town_of_zone; top up from surplus neutral towns if a
        # forced placement failed (rare: no legal anchor in the zone) — matches legacy
        # build()'s fallback so a player is never left without a start town.
        player_towns: list[PlacedObject] = []
        for lvl, zid in player_zids:
            t = all_town_of_zone.get(lvl, {}).get(zid)
            if t is not None:
                player_towns.append(t)
        if self.players:
            spare = [o for o in all_objs if o.purpose == "TOWN" and o not in player_towns]
            player_towns += spare[: max(0, self.players - len(player_towns))]
            player_towns = player_towns[: self.players]
        self.player_towns = player_towns

        if ledger.missing:
            print(f"  WARNING: mine coverage incomplete — missing {sorted(ledger.missing)}")

        map_state.add_objs(self.objs, TerrainGate(ontology))
        map_state.player_towns = self.player_towns
        self._ctx.provide(TownsIndex(player_zids=self.player_zids))

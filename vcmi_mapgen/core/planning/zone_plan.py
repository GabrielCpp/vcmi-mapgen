"""The zone plan every placement step shares: each zone's entrances and walkable web, the
ridge, the planned sea objects, one open shipyard landing per shore, and the player zones with
room kept for their town. VegetationStep builds it before growing trees, and GameplayStep
commits the sea objects."""

from __future__ import annotations

import collections
from collections.abc import Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import final

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.components import STEPS4
from vcmi_mapgen.core.grid.geometry import NB8, edge_dist
from vcmi_mapgen.core.grid.paths import geodesic_path
from vcmi_mapgen.core.grid.segment import ZoneLabel
from vcmi_mapgen.core.model import Identity, PlacedObject, Tile, Zone
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.pipeline import LevelWorkspace, PlacementWorkspace, ZoneWorkspace
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.placement.footprint import footprint_cells
from vcmi_mapgen.core.placement.guards import inflate_gap
from vcmi_mapgen.core.placement.site import door_cells, path_to_web
from vcmi_mapgen.core.planning.entrances import plan_entrances
from vcmi_mapgen.core.priors.gameplay import TerrainStats
from vcmi_mapgen.core.steps.gameplay import mines as MN
from vcmi_mapgen.core.steps.gameplay import shipyards as SH
from vcmi_mapgen.core.steps.gameplay import water as WT
from vcmi_mapgen.core.steps.segment.result import Segmentation
from vcmi_mapgen.core.steps.terrain_gen.result import TerrainGrids
from vcmi_mapgen.core.steps.vegetation import sample as PP
from vcmi_mapgen.corpus.gameplay import load_gameplay

NO_TILES: frozenset[Tile] = frozenset()

MIN_AREA = 25


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


def seaport_cells(objs: Iterable[PlacedObject]) -> tuple[set[Tile], set[Tile]]:
    seaport_blk: set[Tile] = set()
    seaport_appr: set[Tile] = set()
    for so in objs:
        if so.type == "shipyard":
            for scx, scy, sblk in FP.anchored_cells(so.footprint, so.x, so.y):
                if sblk:
                    seaport_blk.add((scx, scy))
            seaport_appr.add((so.x - 1, so.y + 1))
    return seaport_blk, seaport_appr


def _connect_landings(lw: LevelWorkspace) -> None:
    for appr in sorted(lw.seaport_appr):
        for _zid, zw in sorted(lw.zones.items()):
            if appr not in zw.ts_full or appr in zw.prot:
                continue
            free = zw.ts - zw.gblocked - lw.seaport_blk
            goals = sorted(
                zw.prot & free, key=lambda t: (abs(t[0] - appr[0]) + abs(t[1] - appr[1]), t)
            )
            path = next((p for g in goals if (p := geodesic_path(appr, g, free))), list[Tile]())
            zw.prot = zw.prot | frozenset(path)


@final
class _LandingCheck:
    """Refuse a landing whose blocking row would cut open land off the web, or leave its own
    approach off the web. Before vegetation every zone tile still counts as walkable."""

    def __init__(self, lw: LevelWorkspace) -> None:
        self.land: set[Tile] = set()
        self.web: set[Tile] = set()
        for zw in lw.zones.values():
            self.land |= zw.ts - zw.gblocked
            self.web |= zw.prot

    def _pocket(self, start: Tile, cut: AbstractSet[Tile]) -> set[Tile]:
        seen = {start}
        q = collections.deque([start])
        while q:
            t = q.popleft()
            if t in self.web:
                return set()
            for dx, dy in STEPS4:
                n = (t[0] + dx, t[1] + dy)
                if n in self.land and n not in cut and n not in seen:
                    seen.add(n)
                    q.append(n)
        return seen

    def accept(self, obj: PlacedObject) -> bool:
        ident = Identity(obj.type, obj.subtype, obj.animation, obj.footprint)
        _allc, blk, approach = footprint_cells(ident, obj.x, obj.y)
        cut = set(blk)
        if approach is None or approach not in self.land or self._pocket(approach, cut):
            return False
        stranded: set[Tile] = set()
        for x, y in sorted(cut):
            for dx, dy in STEPS4:
                n = (x + dx, y + dy)
                if n in self.land and n not in cut and n not in stranded:
                    stranded |= self._pocket(n, cut)
        return len(stranded) <= SH.SHORE_NOOK


def plan_landings(
    lw: LevelWorkspace, grid: Sequence[Sequence[int]], zones: Mapping[int, Zone], sea: SeaPlan
) -> None:
    """Keep one shipyard landing per shore open for vegetation: the footprint and approach
    of a shipyard the shore could take before any tree stands, joined to the walkable web."""
    reserved = frozenset[Tile]().union(*(zw.ent_bands for zw in lw.zones.values()))
    landings = WT.ensure_water_seaports(
        WT.SeaMap(
            len(grid[0]) if grid else 0,
            len(grid),
            grid,
            zones,
            reserved,
            accept=_LandingCheck(lw).accept,
            quiet=True,
        ),
        list(sea.objs),
        sea.seed,
        sea.catalog,
    )
    _, appr = seaport_cells(landings)
    lw.seaport_blk = frozenset(
        (x, y) for o in landings for x, y, _b in FP.anchored_cells(o.footprint, o.x, o.y)
    )
    lw.seaport_appr = frozenset(appr)
    _connect_landings(lw)


@dataclass(frozen=True, slots=True)
class SeaPlan:
    objs: Sequence[PlacedObject]
    seed: int
    catalog: Catalog


def _water_bodies(grid: Sequence[Sequence[int]]) -> list[set[Tile]]:
    water = {(x, y) for y, row in enumerate(grid) for x, c in enumerate(row) if c == Terrain.WATER}
    seen: set[Tile] = set()
    bodies: list[set[Tile]] = []
    for t0 in sorted(water):
        if t0 in seen:
            continue
        comp, q = {t0}, [t0]
        while q:
            x, y = q.pop()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (x + dx, y + dy)
                if n in water and n not in comp:
                    comp.add(n)
                    q.append(n)
        seen |= comp
        bodies.append(comp)
    return bodies


def populate_water(
    catalog: Catalog, grid: Sequence[Sequence[int]], zones: Mapping[int, Zone], seed: int
) -> list[PlacedObject]:
    objs: list[PlacedObject] = []
    for wi, comp in enumerate(_water_bodies(grid)):
        if len(comp) >= MIN_AREA:
            wobjs = WT.place_water(catalog, comp, zones, 1000 + wi, seed=seed)
            objs.extend(wobjs)
            print(f"  sea  {wi:>3} water    {len(comp):>5} tiles: {len(wobjs):>3} sea objects")
    return objs


@dataclass(frozen=True, slots=True)
class _LevelPlan:
    catalog: Catalog
    zones: Mapping[int, Zone]
    zone_label: ZoneLabel
    tunnel_protect: AbstractSet[Tile]
    gstats: Mapping[str, TerrainStats]


@final
class _ZonePlanner:
    def __init__(self, lp: _LevelPlan) -> None:
        self.lp = lp
        self.entrance_plan = plan_entrances(lp.zone_label)
        self.rim_all = _rim8(lp.zones)
        self.ridge: set[Tile] = set()

    def workspace(self, zid: int, z: Zone, terrain: str) -> ZoneWorkspace:
        lp = self.lp
        ts = set(z.tiles_set)
        z_entr = self.entrance_plan.get(zid, [])
        zcx, zcy = z.centroid
        seedt = min(ts, key=lambda t: (t[0] - round(zcx)) ** 2 + (t[1] - round(zcy)) ** 2)
        ent_bands: set[Tile] = set[Tile]().union(*(b for _r, b, _o in z_entr)) if z_entr else set()
        rim8 = self.rim_all & ts
        self.ridge |= rim8 - ent_bands
        prot = PP.protected_web(
            PP.ZoneRef(ts, lp.zone_label, zid, z.centroid),
            edge_dist(ts),
            seedt,
            PP.WebOptions(
                open_frac=lp.gstats[terrain].border_open_frac,
                entrances=z_entr,
                keep_off=rim8,
            ),
        ) | (lp.tunnel_protect & ts)
        return ZoneWorkspace(
            terrain=terrain,
            ts=frozenset(ts),
            ts_full=frozenset(ts),
            entrances=z_entr,
            prot=frozenset(prot),
            rim8=frozenset(rim8),
            ent_bands=frozenset(ent_bands),
        )

    def level(self) -> LevelWorkspace:
        zws: dict[int, ZoneWorkspace] = {}
        for zid, z in sorted(self.lp.zones.items()):
            if z.terrain_type.is_barrier or z.area < MIN_AREA:
                continue
            zws[zid] = self.workspace(zid, z, self.lp.catalog.terrain_name(z.terrain_type))
        return LevelWorkspace(
            zones=zws, entrance_plan=self.entrance_plan, ridge=frozenset(self.ridge)
        )


@dataclass(frozen=True, slots=True)
class TownRoom:
    cells: frozenset[Tile]
    clear: frozenset[Tile]
    blk: frozenset[Tile]
    path: tuple[Tile, ...]


def town_room(catalog: Catalog, zw: ZoneWorkspace, off: AbstractSet[Tile]) -> TownRoom | None:
    """The town spot nearest the zone centre before any tree grows: the footprint and approach
    inside the zone and clear of ``off``, the blocking cells off the web, and a walk from the
    approach to the web."""
    ident = catalog.identity_of(MN.RND_TOWN)
    area = len(zw.ts)
    cx = sum(t[0] for t in zw.ts) / area + (ident.footprint.width - 1) / 2.0
    cy = sum(t[1] for t in zw.ts) / area + (ident.footprint.height - 1) / 2.0
    for anchor in sorted(zw.ts, key=lambda t: ((t[0] - cx) ** 2 + (t[1] - cy) ** 2, t)):
        allc, blk, approach = footprint_cells(ident, *anchor)
        if approach is None:
            continue
        cells = frozenset([*allc, approach])
        if any(t not in zw.ts or t in off for t in cells):
            continue
        if any(t in zw.prot for t in blk):
            continue
        path = path_to_web(approach, zw.prot, zw.ts - zw.gblocked - set(blk))
        if path:
            clear = frozenset([*blk, *door_cells(ident, anchor), approach])
            return TownRoom(cells, clear, frozenset(blk), tuple(path))
    return None


def _room_off(lw: LevelWorkspace, zw: ZoneWorkspace, tunnels: AbstractSet[Tile]) -> set[Tile]:
    off = set(zw.ent_bands) | set(tunnels)
    inflate_gap(off, lw.seaport_blk | lw.seaport_appr)
    return off


def plan_player_zones(
    catalog: Catalog,
    workspace: PlacementWorkspace,
    zones_by_level: Mapping[int, Mapping[int, Zone]],
    tunnels: AbstractSet[Tile],
    players: int,
) -> None:
    """Pick the player zones among those with room for a town, and keep that room: the town's
    blocking cells, door and approach stay free of vegetation, count as walls when vegetation
    keeps its ground reachable, and its approach joins the web."""
    rooms: dict[tuple[int, int], TownRoom | None] = {}

    def room(level: int, zid: int) -> TownRoom | None:
        if (level, zid) not in rooms:
            lw = workspace.levels.get(level)
            zw = lw.zones.get(zid) if lw is not None else None
            off = (
                NO_TILES
                if zw is None or lw is None
                else _room_off(lw, zw, tunnels if level == 1 else NO_TILES)
            )
            rooms[level, zid] = None if zw is None else town_room(catalog, zw, off)
        return rooms[level, zid]

    picks = MN.select_player_zones(
        zones_by_level, players, lambda level, zid: room(level, zid) is not None
    )
    for level, zid in picks:
        kept = room(level, zid)
        if kept is None:
            continue
        zw = workspace.levels[level].zones[zid]
        zw.town_room = kept.cells
        zw.town_clear = kept.clear
        zw.town_blk = kept.blk
        zw.prot = zw.prot | frozenset(kept.path)
    if players and len(picks) < players:
        print(f"  WARNING: only {len(picks)} zones can host a player town (requested {players})")
    workspace.player_zids = picks


def plan_zones(
    catalog: Catalog,
    workspace: PlacementWorkspace,
    segmentation: Segmentation,
    terrain: TerrainGrids,
    seed: int,
) -> None:
    """Fill ``workspace`` with one ``LevelWorkspace`` per terrain level. The surface level
    also holds its planned sea objects and the shipyard landings kept open for them."""
    for level in sorted(terrain.grids):
        zones = segmentation.zones[level]
        planner = _ZonePlanner(
            _LevelPlan(
                catalog,
                zones,
                segmentation.zone_label[level],
                terrain.tunnel_protect if level == 1 else NO_TILES,
                load_gameplay(level=level),
            )
        )
        lw = planner.level()
        workspace.levels[level] = lw
        if level == 0:
            lw.sea = tuple(populate_water(catalog, terrain.grids[level], zones, seed))
            plan_landings(lw, terrain.grids[level], zones, SeaPlan(lw.sea, seed, catalog))

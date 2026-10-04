"""The zone plan every placement step shares: each zone's entrances and walkable web, the
planned sea objects, one open shipyard landing per shore, and the player zones with room kept
for their town. VegetationStep builds it before growing trees and publishes it as a
``ZonePlan``, and GameplayStep commits the sea objects."""

from __future__ import annotations

import collections
from collections.abc import Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field, replace
from typing import final

from vcmi_mapgen.core.catalog import Catalog, Trait
from vcmi_mapgen.core.grid.geometry import NB8, edge_dist
from vcmi_mapgen.core.grid.paths import geodesic_path
from vcmi_mapgen.core.grid.reach import STEPS4
from vcmi_mapgen.core.grid.segment import ZoneLabel
from vcmi_mapgen.core.model import Entrance, PlacedObject, Tile, Zone
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.placement import water as WT
from vcmi_mapgen.core.placement.footprint import footprint_cells, overlay_cells
from vcmi_mapgen.core.placement.guards import inflate_gap
from vcmi_mapgen.core.placement.site import door_cells, path_to_web
from vcmi_mapgen.core.planning.entrances import Passages, all_passages
from vcmi_mapgen.core.planning.player_zones import select_player_zones
from vcmi_mapgen.core.planning.web import WebOptions, ZoneRef, protected_web
from vcmi_mapgen.core.priors.gameplay import GameplayStats, TerrainStats

NO_TILES: frozenset[Tile] = frozenset()

MIN_AREA = 25


@dataclass(frozen=True, slots=True)
class TownRoom:
    cells: frozenset[Tile]
    clear: frozenset[Tile]
    blk: frozenset[Tile]
    path: tuple[Tile, ...]


NO_ROOM = TownRoom(NO_TILES, NO_TILES, NO_TILES, ())


@dataclass(frozen=True, slots=True)
class PlanZone:
    """One zone before any tree grows: its terrain and tiles, its planned entrances and their
    bands, its 8-connected rim, the walkable web, and the room kept for a player town
    (``NO_ROOM`` in any other zone)."""

    terrain: str
    ts: frozenset[Tile]
    entrances: tuple[Entrance, ...]
    prot: frozenset[Tile]
    rim8: frozenset[Tile]
    ent_bands: frozenset[Tile]
    town: TownRoom = NO_ROOM


@dataclass(frozen=True, slots=True)
class Landings:
    """The shipyard cells of a level: the blocking or anchored cells and the approaches."""

    blk: frozenset[Tile] = NO_TILES
    appr: frozenset[Tile] = NO_TILES


@dataclass(frozen=True, slots=True)
class PlanLevel:
    """One level of the plan: its zones, the entrance plan over all its zones, the planned
    sea objects, the landings kept open for them and the zone pairs whose border is open.
    Only the surface has sea."""

    zones: Mapping[int, PlanZone]
    entrance_plan: Mapping[int, Sequence[Entrance]]
    sea: tuple[PlacedObject, ...] = ()
    landings: Landings = Landings()
    open_pairs: frozenset[tuple[int, int]] = frozenset()


@dataclass(frozen=True, slots=True)
class ZonePlan:
    """The plan VegetationStep publishes: one ``PlanLevel`` per terrain level, and the
    player zones as (level, zid)."""

    levels: Mapping[int, PlanLevel]
    player_zids: tuple[tuple[int, int], ...]


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


def seaport_cells(catalog: Catalog, objs: Iterable[PlacedObject]) -> tuple[set[Tile], set[Tile]]:
    seaport_blk: set[Tile] = set()
    seaport_appr: set[Tile] = set()
    for so in objs:
        if catalog.identity_of(so.kind).type in catalog.types_with(Trait.SHIPYARD):
            for scx, scy, sblk in FP.anchored_cells(so.footprint, so.x, so.y):
                if sblk:
                    seaport_blk.add((scx, scy))
            seaport_appr.add((so.x - 1, so.y + 1))
    return seaport_blk, seaport_appr


def _connect_landings(zones: Mapping[int, PlanZone], landings: Landings) -> dict[int, PlanZone]:
    out = dict(zones)
    for appr in sorted(landings.appr):
        for zid in sorted(out):
            zone = out[zid]
            if appr not in zone.ts or appr in zone.prot:
                continue
            free = zone.ts - landings.blk
            goals = sorted(
                zone.prot & free, key=lambda t: (abs(t[0] - appr[0]) + abs(t[1] - appr[1]), t)
            )
            path = next((p for g in goals if (p := geodesic_path(appr, g, free))), list[Tile]())
            out[zid] = replace(zone, prot=zone.prot | frozenset(path))
    return out


@final
class _LandingCheck:
    """Refuse a landing whose blocking row would cut open land off the web, or leave its own
    approach off the web. Before vegetation every zone tile still counts as walkable."""

    def __init__(self, zones: Mapping[int, PlanZone]) -> None:
        self.land: set[Tile] = set()
        self.web: set[Tile] = set()
        for zone in zones.values():
            self.land |= zone.ts
            self.web |= zone.prot

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
        _allc, blk, approach = footprint_cells(obj.footprint, obj.x, obj.y)
        cut = set(blk)
        if approach is None or approach not in self.land or self._pocket(approach, cut):
            return False
        stranded: set[Tile] = set()
        for x, y in sorted(cut):
            for dx, dy in STEPS4:
                n = (x + dx, y + dy)
                if n in self.land and n not in cut and n not in stranded:
                    stranded |= self._pocket(n, cut)
        return len(stranded) <= WT.SHORE_NOOK


def plan_landings(
    pl: PlanLevel, grid: Sequence[Sequence[int]], zones: Mapping[int, Zone], sea: SeaPlan
) -> PlanLevel:
    """Keep one shipyard landing per shore open for vegetation: the footprint and approach
    of a shipyard the shore could take before any tree stands, joined to the walkable web."""
    reserved = frozenset[Tile]().union(*(z.ent_bands for z in pl.zones.values()))
    landings = WT.ensure_water_seaports(
        WT.SeaMap(
            len(grid[0]) if grid else 0,
            len(grid),
            grid,
            zones,
            reserved,
            accept=_LandingCheck(pl.zones).accept,
            quiet=True,
        ),
        list(sea.objs),
        sea.seed,
        sea.catalog,
    )
    _, appr = seaport_cells(sea.catalog, landings)
    kept = Landings(
        frozenset(
            (x, y) for o in landings for x, y, _b in FP.anchored_cells(o.footprint, o.x, o.y)
        ),
        frozenset(appr),
    )
    return replace(pl, sea=tuple(sea.objs), landings=kept, zones=_connect_landings(pl.zones, kept))


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
    catalog: Catalog, grid: Sequence[Sequence[int]], st: TerrainStats | None, seed: int
) -> list[PlacedObject]:
    objs: list[PlacedObject] = []
    for wi, comp in enumerate(_water_bodies(grid)):
        if len(comp) >= MIN_AREA:
            wobjs = WT.place_water(catalog, st, comp, 1000 + wi, seed=seed)
            objs.extend(wobjs)
            print(f"  sea  {wi:>3} water    {len(comp):>5} tiles: {len(wobjs):>3} sea objects")
    return objs


@dataclass(frozen=True, slots=True)
class _LevelPlan:
    catalog: Catalog
    zones: Mapping[int, Zone]
    zone_label: ZoneLabel
    passages: Passages
    tunnel_protect: AbstractSet[Tile]
    gstats: Mapping[str, TerrainStats]


@final
class _ZonePlanner:
    def __init__(self, lp: _LevelPlan) -> None:
        self.lp = lp
        self.entrance_plan = lp.passages.entrances
        self.rim_all = _rim8(lp.zones)

    def zone(self, zid: int, z: Zone, terrain: str) -> PlanZone:
        lp = self.lp
        ts = set(z.tiles_set)
        z_entr = self.entrance_plan.get(zid, [])
        zcx, zcy = z.centroid
        seedt = min(ts, key=lambda t: (t[0] - round(zcx)) ** 2 + (t[1] - round(zcy)) ** 2)
        ent_bands: set[Tile] = set[Tile]().union(*(b for _r, b, _o in z_entr)) if z_entr else set()
        rim8 = self.rim_all & ts
        prot = protected_web(
            ZoneRef(ts, lp.zone_label, zid, z.centroid),
            edge_dist(ts),
            seedt,
            WebOptions(
                open_frac=lp.gstats[terrain].border_open_frac,
                entrances=z_entr,
                keep_off=rim8,
            ),
        ) | (lp.tunnel_protect & ts)
        return PlanZone(
            terrain=terrain,
            ts=frozenset(ts),
            entrances=tuple(z_entr),
            prot=frozenset(prot),
            rim8=frozenset(rim8),
            ent_bands=frozenset(ent_bands),
        )

    def level(self) -> PlanLevel:
        zones: dict[int, PlanZone] = {}
        for zid, z in sorted(self.lp.zones.items()):
            if z.terrain_type.is_barrier or z.area < MIN_AREA:
                continue
            zones[zid] = self.zone(zid, z, self.lp.catalog.terrain_name(z.terrain_type))
        return PlanLevel(
            zones=zones, entrance_plan=self.entrance_plan, open_pairs=self.lp.passages.open_pairs
        )


def town_room(
    catalog: Catalog, zone: PlanZone, off: AbstractSet[Tile], size: int = 0
) -> TownRoom | None:
    """The town spot nearest the zone centre before any tree grows: the footprint and approach
    inside the zone and clear of ``off``, the blocking cells off the web, and a walk from the
    approach to the web. Given the map ``size``, the sprite's overlay cells block nothing, so
    they may lie anywhere on the map, outside the zone and on ``off``."""
    ident = catalog.random_town()
    area = len(zone.ts)
    cx = sum(t[0] for t in zone.ts) / area + (ident.footprint.width - 1) / 2.0
    cy = sum(t[1] for t in zone.ts) / area + (ident.footprint.height - 1) / 2.0
    for anchor in sorted(zone.ts, key=lambda t: ((t[0] - cx) ** 2 + (t[1] - cy) ** 2, t)):
        allc, blk, approach = footprint_cells(ident.footprint, *anchor)
        if approach is None:
            continue
        cells = frozenset([*allc, approach])
        held = cells - overlay_cells(ident.footprint, anchor) if size else cells
        if any(t not in zone.ts or t in off for t in held):
            continue
        if any(not (0 <= x < size and 0 <= y < size) for x, y in cells - held):
            continue
        if any(t in zone.prot for t in blk):
            continue
        path = path_to_web(approach, zone.prot, zone.ts - set(blk))
        if path:
            clear = frozenset([*blk, *door_cells(ident.footprint, anchor), approach])
            return TownRoom(cells, clear, frozenset(blk), tuple(path))
    return None


def _room_off(landings: Landings, zone: PlanZone, tunnels: AbstractSet[Tile]) -> set[Tile]:
    off = set(zone.ent_bands) | set(tunnels)
    inflate_gap(off, landings.blk | landings.appr)
    return off


@dataclass(frozen=True, slots=True)
class HomeRequest:
    """How many player zones to pick, the ``(level, zid)`` zones to try first, and the map
    side a preferred zone's town may spread its overlay cells over."""

    players: int
    preferred: Sequence[tuple[int, int]] = ()
    size: int = 0


def plan_player_zones(
    catalog: Catalog,
    levels: Mapping[int, PlanLevel],
    zones_by_level: Mapping[int, Mapping[int, Zone]],
    tunnels: AbstractSet[Tile],
    homes: HomeRequest,
) -> ZonePlan:
    """Pick the player zones among those with room for a town, the preferred ones first, and
    keep that room: the town's blocking cells, door and approach stay free of vegetation,
    count as walls when vegetation keeps its ground reachable, and its approach joins the web.
    A preferred zone's town may lay its overlay cells anywhere on the map."""
    players, preferred = homes.players, homes.preferred
    rooms: dict[tuple[int, int], TownRoom | None] = {}

    def room(level: int, zid: int) -> TownRoom | None:
        if (level, zid) not in rooms:
            pl = levels.get(level)
            zone = pl.zones.get(zid) if pl is not None else None
            off = (
                NO_TILES
                if zone is None or pl is None
                else _room_off(pl.landings, zone, tunnels if level == 1 else NO_TILES)
            )
            loose = homes.size if (level, zid) in preferred else 0
            rooms[level, zid] = None if zone is None else town_room(catalog, zone, off, loose)
        return rooms[level, zid]

    picks = select_player_zones(
        zones_by_level, players, lambda level, zid: room(level, zid) is not None, preferred
    )
    zones = {level: dict(pl.zones) for level, pl in levels.items()}
    for level, zid in picks:
        kept = room(level, zid)
        if kept is None:
            continue
        zone = zones[level][zid]
        zones[level][zid] = replace(zone, town=kept, prot=zone.prot | frozenset(kept.path))
    if players and len(picks) < players:
        print(f"  WARNING: only {len(picks)} zones can host a player town (requested {players})")
    return ZonePlan(
        {level: replace(pl, zones=zones[level]) for level, pl in levels.items()}, tuple(picks)
    )


@dataclass(frozen=True, slots=True)
class PlanTerrain:
    """What a zone plan reads of the terrain: each level's zones and zone label grid, each
    level's ``Terrain`` grid, the underground tunnel cells and each level's passages. A
    level with no passages gets ``all_passages`` over its zone label."""

    zones: Mapping[int, Mapping[int, Zone]]
    zone_label: Mapping[int, ZoneLabel]
    grids: Mapping[int, list[list[Terrain]]]
    tunnel_protect: frozenset[Tile]
    passages: Mapping[int, Passages] = field(default_factory=dict[int, Passages])


def plan_zones(
    catalog: Catalog, terrain: PlanTerrain, gameplay: Mapping[int, GameplayStats], seed: int
) -> dict[int, PlanLevel]:
    """One ``PlanLevel`` per terrain level, read against that level's ``gameplay``
    statistics. The surface level also holds its planned sea objects and the shipyard
    landings kept open for them."""
    levels: dict[int, PlanLevel] = {}
    for level in sorted(terrain.grids):
        zones = terrain.zones[level]
        label = terrain.zone_label[level]
        passages = terrain.passages.get(level)
        planner = _ZonePlanner(
            _LevelPlan(
                catalog,
                zones,
                label,
                all_passages(label) if passages is None else passages,
                terrain.tunnel_protect if level == 1 else NO_TILES,
                gameplay[level],
            )
        )
        pl = planner.level()
        if level == 0:
            water = gameplay[0].get("water")
            sea = tuple(populate_water(catalog, terrain.grids[level], water, seed))
            pl = plan_landings(pl, terrain.grids[level], zones, SeaPlan(sea, seed, catalog))
        levels[level] = pl
    return levels

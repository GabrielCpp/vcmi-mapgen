"""Shipyards placed against the vegetated surface field. The shore planner in ``water`` picks
the shores and the candidate anchors. These hooks decide which anchors are legal, rank them
by back contact and commit the chosen one into the zone sites it touches. An anchor is
illegal when a solid cell stands on a terrain the shipyard may not stand on. A shipyard may
cross a zone rim, so the zone owning its approach links it to the web and every zone it
touches keeps its reachable tiles reachable. A hero boards the shipyard's boat from an open land
tile beside the water the shipyard docks on, so an anchor with no such tile is illegal too."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import final

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Footprint, Identity, PlacedObject, Tile, Zone
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.placement import water as WT
from vcmi_mapgen.core.placement.footprint import footprint_cells
from vcmi_mapgen.core.placement.ground import on_ground, solid_tiles
from vcmi_mapgen.core.placement.guards import Fit
from vcmi_mapgen.core.placement.site import SiteIndex, ZoneSite, back_score, door_cells

type Boarding = tuple[Tile, Tile]


def _ring(t: Tile) -> list[Tile]:
    return [(t[0] + dx, t[1] + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]


def boardings(
    solid: Iterable[Tile], afloat: Callable[[Tile], bool], ashore: Callable[[Tile], bool]
) -> list[Boarding]:
    """Each dock beside a solid cell of a shipyard paired with each land tile a hero boards
    from there. A dock is a tile around a solid cell where a boat floats."""
    docks = sorted({d for c in solid for d in _ring(c) if afloat(d)})
    return [(d, t) for d in docks for t in _ring(d) if ashore(t)]


def _any(_boarding: Boarding) -> bool:
    return True


@dataclass(frozen=True, slots=True)
class _Pending:
    owner: ZoneSite
    fit: Fit
    reaches: tuple[tuple[ZoneSite, set[Tile]], ...]


@final
class _ShipyardHooks:
    def __init__(
        self,
        idx: SiteIndex,
        catalog: Catalog,
        shore: Shore,
        fit: Callable[[Boarding], bool] = _any,
    ) -> None:
        self.idx = idx
        self.catalog = catalog
        self.lf = idx.lf
        self.shore = shore
        self.fit = fit
        self.moored = {t for o in shore.objs for t, role in o.footprint.at(o.x, o.y) if role.blocks}
        self.pending: dict[Tile, _Pending] = {}
        self.banned: set[Tile] = set()
        for site in idx.sites.values():
            self.banned |= site.zone.ent_bands | set(site.approaches) | site.cells

    def _door_ok(self, fp: Footprint, anchor: Tile, approach: Tile) -> ZoneSite | None:
        lf = self.lf
        owner = self.idx.site_at(approach)
        if owner is None or approach not in owner.reach or approach in lf.occupied:
            return None
        if not lf.walkable(approach) or approach in self.banned:
            return None
        if not all(lf.walkable(t) for t in door_cells(fp, anchor)):
            return None
        return owner

    def _cells_ok(self, allc: Sequence[Tile], blk: Sequence[Tile]) -> bool:
        lf = self.lf
        if any(t in lf.near for t in blk):
            return False
        return not any(
            t in lf.occupied or t in lf.avoid or t in self.banned or self.idx.site_at(t) is None
            for t in allc
        )

    def accept(self, obj: PlacedObject) -> bool:
        anchor = (obj.x, obj.y)
        allc, blk, approach = footprint_cells(obj.footprint, *anchor)
        if approach is None or not self._cells_ok(allc, blk):
            return False
        solid = solid_tiles(obj.footprint, anchor)
        if not on_ground(self.catalog, obj.kind, solid, self.lf.ground):
            return False
        owner = self._door_ok(obj.footprint, anchor, approach)
        if owner is None or not self.lf.accepts(obj):
            return False
        touched = {id(s): s for t in allc if (s := self.idx.site_at(t)) is not None}
        touched[id(owner)] = owner
        reaches: list[tuple[ZoneSite, set[Tile]]] = []
        for site in touched.values():
            reach = site.reach_without(blk, WT.SHORE_NOOK)
            if reach is None or (site is owner and approach not in reach):
                return False
            reaches.append((site, reach))
        if not any(self.fit(b) for b in self._boardings(solid, set(allc), reaches)):
            return False
        self.pending[anchor] = _Pending(owner, (allc, blk, approach), tuple(reaches))
        return True

    def _boardings(
        self,
        solid: Iterable[Tile],
        cells: AbstractSet[Tile],
        reaches: Sequence[tuple[ZoneSite, set[Tile]]],
    ) -> list[Boarding]:
        lf, grid = self.lf, self.shore.grid
        after = {id(site): reach for site, reach in reaches}

        def afloat(t: Tile) -> bool:
            return lf.on_map(t) and grid[t[1]][t[0]] == Terrain.WATER and t not in self.moored

        def ashore(t: Tile) -> bool:
            if not lf.on_map(t) or t in cells or t in lf.occupied or not lf.walkable(t):
                return False
            site = self.idx.site_at(t)
            return site is not None and t in after.get(id(site), site.reach)

        return boardings(solid, afloat, ashore)

    def score(self, ident: Identity, anchor: Tile) -> int:
        return back_score(ident.footprint, anchor, self.lf.unwalkable, self.lf.size)

    def placed(self, obj: PlacedObject) -> None:
        obj.level = self.lf.level
        p = self.pending.pop((obj.x, obj.y))
        allc, blk, _approach = p.fit
        for site, reach in p.reaches:
            if site is p.owner:
                continue
            site.cells.update(t for t in allc if t in site.ts)
            site.block(blk, reach)
        owner_reach = next(r for s, r in p.reaches if s is p.owner)
        p.owner.commit(obj, p.fit, owner_reach)
        self.banned |= set(allc) | set(p.owner.approaches)


@dataclass(frozen=True, slots=True)
class Shore:
    """One level's terrain, zones and the gameplay and sea objects already placed on it."""

    grid: Sequence[Sequence[int]]
    zones: Mapping[int, Zone]
    objs: list[PlacedObject]


def _sea(shore: Shore, hooks: _ShipyardHooks) -> WT.SeaMap:
    grid = shore.grid
    return WT.SeaMap(
        len(grid[0]) if grid else 0,
        len(grid),
        grid,
        shore.zones,
        accept=hooks.accept,
        score=hooks.score,
        placed=hooks.placed,
    )


def place_shipyards(idx: SiteIndex, shore: Shore, seed: int, catalog: Catalog) -> int:
    """Guarantee a shipyard on every shore the water planner requires one on. Returns how
    many were added."""
    hooks = _ShipyardHooks(idx, catalog, shore)
    return len(WT.ensure_water_seaports(_sea(shore, hooks), shore.objs, seed, catalog))


@dataclass(frozen=True, slots=True)
class Link:
    """The land a linking shipyard stands on and the boardings it accepts."""

    land: AbstractSet[Tile]
    fit: Callable[[Boarding], bool]


def place_link(
    idx: SiteIndex, shore: Shore, seed: int, catalog: Catalog, link: Link
) -> PlacedObject | None:
    """One shipyard on the coast of the link's land with a boarding its fit accepts. None when
    no anchor fits."""
    hooks = _ShipyardHooks(idx, catalog, shore, link.fit)
    return WT.seaport_on(_sea(shore, hooks), shore.objs, seed, catalog, link.land)

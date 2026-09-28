"""Shipyards placed against the vegetated surface field. The shore planner in ``water`` picks
the shores and the candidate anchors. These hooks decide which anchors are legal, rank them
by back contact and commit the chosen one into the zone sites it touches. A shipyard may
cross a zone rim, so the zone owning its approach links it to the web and every zone it
touches keeps its reachable tiles reachable."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import final

from vcmi_mapgen.models import Identity, PlacedObject, Tile, Zone
from vcmi_mapgen.ontology import Ontology
from vcmi_mapgen.steps.gameplay import water as WT
from vcmi_mapgen.steps.gameplay.site import SiteIndex, ZoneSite, back_score, door_cells
from vcmi_mapgen.steps.gate.gates import Fit, footprint_cells

SHORE_NOOK = 4


@dataclass(frozen=True, slots=True)
class _Pending:
    owner: ZoneSite
    fit: Fit
    reaches: tuple[tuple[ZoneSite, set[Tile]], ...]


def _identity(obj: PlacedObject) -> Identity:
    return Identity(obj.type, obj.subtype, obj.animation, obj.mask)


@final
class _ShipyardHooks:
    def __init__(self, idx: SiteIndex) -> None:
        self.idx = idx
        self.lf = idx.lf
        self.pending: dict[Tile, _Pending] = {}
        self.banned: set[Tile] = set()
        for site in idx.sites.values():
            self.banned |= site.zw.ent_bands | set(site.approaches) | site.cells

    def _door_ok(self, ident: Identity, anchor: Tile, approach: Tile) -> ZoneSite | None:
        lf = self.lf
        owner = self.idx.site_at(approach)
        if owner is None or approach not in owner.reach or approach in lf.occupied:
            return None
        if not lf.walkable(approach) or approach in self.banned:
            return None
        if not all(lf.walkable(t) for t in door_cells(ident, anchor)):
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
        ident, anchor = _identity(obj), (obj.x, obj.y)
        allc, blk, approach = footprint_cells(ident, *anchor)
        if approach is None or not self._cells_ok(allc, blk):
            return False
        owner = self._door_ok(ident, anchor, approach)
        if owner is None or not self.lf.accepts(obj):
            return False
        touched = {id(s): s for t in allc if (s := self.idx.site_at(t)) is not None}
        touched[id(owner)] = owner
        reaches: list[tuple[ZoneSite, set[Tile]]] = []
        for site in touched.values():
            reach = site.reach_without(blk, SHORE_NOOK)
            if reach is None or (site is owner and approach not in reach):
                return False
            reaches.append((site, reach))
        self.pending[anchor] = _Pending(owner, (allc, blk, approach), tuple(reaches))
        return True

    def score(self, ident: Identity, anchor: Tile) -> int:
        return back_score(ident, anchor, self.lf.unwalkable, self.lf.size)

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
        p.owner.spent += 1
        self.banned |= set(allc) | set(p.owner.approaches)


@dataclass(frozen=True, slots=True)
class Shore:
    """One level's terrain, zones and the gameplay and sea objects already placed on it."""

    grid: Sequence[Sequence[int]]
    zones: Mapping[int, Zone]
    objs: list[PlacedObject]


def place_shipyards(idx: SiteIndex, shore: Shore, seed: int, ontology: Ontology) -> int:
    """Guarantee a shipyard on every shore the water planner requires one on. Returns how
    many were added."""
    hooks = _ShipyardHooks(idx)
    grid = shore.grid
    sea = WT.SeaMap(
        len(grid[0]) if grid else 0,
        len(grid),
        grid,
        shore.zones,
        accept=hooks.accept,
        score=hooks.score,
        placed=hooks.placed,
    )
    return len(WT.ensure_water_seaports(sea, shore.objs, seed, ontology))

"""One level as the roads read it: the walkable ground once every object stands, the places
and passages the terrain planned, each player town's approach and each place's sites."""

import collections
import random
from collections.abc import Iterable, Sequence
from collections.abc import Set as AbstractSet

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.geometry import NB8
from vcmi_mapgen.core.grid.segment import ZoneLabel
from vcmi_mapgen.core.model import MapState, PlacedObject, Role, Tile, footprint
from vcmi_mapgen.core.model.purpose import FLANKED, Purpose
from vcmi_mapgen.core.model.road import Road
from vcmi_mapgen.core.priors.places import RoadStats
from vcmi_mapgen.core.reading.ground import Ground, purpose_of
from vcmi_mapgen.core.steps.roads.layer import RoadLevel, RoadPlace
from vcmi_mapgen.core.steps.terrain_gen.result import LevelPlaces

SITE_PURPOSES = (Purpose.TOWN, Purpose.MINE, Purpose.DWELLING)


def visit_tile(obj: PlacedObject, walk: AbstractSet[Tile]) -> Tile | None:
    """The walkable tile a hero visits ``obj`` from: its approach, else one of its
    interactive cells, else a walkable neighbour of one, the least in tile order."""
    cells = footprint(obj)
    for roles in ((Role.APPROACH,), (Role.VISIT, Role.ENTRANCE)):
        tiles = sorted(t for t, role in cells if role in roles and t in walk)
        if tiles:
            return tiles[0]
    near = sorted(
        (x + dx, y + dy)
        for (x, y), role in cells
        if role.interactive
        for dx, dy in NB8
        if (x + dx, y + dy) in walk
    )
    return near[0] if near else None


def _label(label: ZoneLabel, t: Tile) -> int:
    return label[t[1]][t[0]]


def homes_of(
    towns: Sequence[PlacedObject], level: int, label: ZoneLabel, walk: AbstractSet[Tile]
) -> tuple[tuple[int, Tile], ...]:
    """Each player town of ``level`` with a walkable visit tile inside a place, as (its
    place, that tile), in player order."""
    out: list[tuple[int, Tile]] = []
    for town in towns:
        t = visit_tile(town, walk) if town.level == level else None
        if t is not None and _label(label, t) >= 0:
            out.append((_label(label, t), t))
    return tuple(out)


def sites_of(
    catalog: Catalog,
    objs: Sequence[PlacedObject],
    players: Sequence[PlacedObject],
    label: ZoneLabel,
    walk: AbstractSet[Tile],
) -> dict[int, tuple[Tile, ...]]:
    """Each place's site visit tiles: its towns that no player owns, then its mines, then
    its dwellings, each group in tile order."""
    owned = {id(t) for t in players}
    by: dict[int, list[tuple[int, Tile]]] = collections.defaultdict(list)
    for obj in objs:
        purpose = purpose_of(catalog, obj)
        if purpose not in SITE_PURPOSES or id(obj) in owned:
            continue
        t = visit_tile(obj, walk)
        if t is not None and _label(label, t) >= 0:
            by[_label(label, t)].append((SITE_PURPOSES.index(Purpose(purpose)), t))
    return {p: tuple(t for _, t in sorted(ts)) for p, ts in sorted(by.items())}


def shy_of(
    catalog: Catalog,
    objs: Sequence[PlacedObject],
    served: AbstractSet[Tile],
    walk: AbstractSet[Tile],
) -> frozenset[Tile]:
    """The walkable sprite tiles of every gameplay object, its approach and the tiles in
    ``served`` left out, so a road reaches an object only where it stops."""
    out: set[Tile] = set()
    for obj in objs:
        if purpose_of(catalog, obj) not in FLANKED:
            continue
        out.update(
            t
            for t, role in footprint(obj)
            if role is not Role.APPROACH and t in walk and t not in served
        )
    return frozenset(out)


def road_level(
    catalog: Catalog,
    ground: Ground,
    places: LevelPlaces,
    map_state: MapState,
    level: int,
) -> RoadLevel:
    """``level`` of ``map_state`` ready for roads, from its ground, its places and its
    objects."""
    walk, players = ground.walk, map_state.player_towns
    objs = [o for o in map_state.objs if o.level == level]
    homes = homes_of(players, level, places.label, walk)
    sites = sites_of(catalog, objs, players, places.label, walk)
    served = {t for _, t in homes} | {t for ts in sites.values() for t in ts}
    return RoadLevel(
        walk=walk,
        terrain=ground.terrain,
        label=places.label,
        places={p: RoadPlace(pl.role, pl.dominant) for p, pl in places.places.items()},
        kinds=places.kinds,
        passages=places.passages,
        homes=homes,
        sites=sites,
        shy=shy_of(catalog, objs, served, walk),
    )


def map_surface(stats: Iterable[RoadStats], rng: random.Random) -> Road:
    counts = [c for s in stats for c in s.surface.values()]
    weights = [sum(c.get(int(r), 0) for c in counts) for r in Road]
    return rng.choices(list(Road), weights)[0] if sum(weights) > 0 else Road.DIRT

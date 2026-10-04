"""Place inference on one level of a corpus or generated map (map-math 3.2): the place map,
each place's role, owner and palette, and the kind of every realised adjacency."""

import collections
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState, Tile
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.reading.borders import (
    AdjacencyKind,
    Crossing,
    Edge,
    Pair,
    adjacency_kind,
    border_pairs,
    crossings,
    merge_regions,
)
from vcmi_mapgen.core.reading.ground import Ground, TownKey, read_ground
from vcmi_mapgen.core.reading.growth import grow_places

POCKET_MAX_AREA = 60
PASS_WIDTH = 6
PASS_DEGREE = 2


class PlaceRole(StrEnum):
    HOME = "home"
    MIDDLE = "middle"
    TREASURE = "treasure"
    PASS = "pass"
    POCKET = "pocket"


@dataclass(frozen=True, slots=True)
class Place:
    """One inferred place. ``towns`` holds the walkable anchor tile of each of its towns,
    ``boundary`` counts its tiles with a 4-neighbour outside it, and ``rewards`` counts
    the reward objects standing in it."""

    role: PlaceRole
    owner: int | None
    area: int
    dominant: Terrain
    terrain: Mapping[Terrain, int]
    boundary: int
    towns: tuple[Tile, ...]
    rewards: int


@dataclass(frozen=True, slots=True)
class Border:
    """The tile pairs between two places, their walkable crossings and the adjacency kind
    read off them."""

    edges: tuple[Edge, ...]
    crossings: tuple[Crossing, ...]
    kind: AdjacencyKind


@dataclass(frozen=True, slots=True)
class InferredPlaces:
    """The place map of one level. ``labels[y][x]`` is the place id of a land tile and -1
    on water and rock. ``places[i]`` is place ``i``. ``adjacency`` maps each sorted pair of
    adjacent place ids to its kind, and ``borders`` holds what the kind was read from."""

    labels: tuple[tuple[int, ...], ...] = ()
    places: tuple[Place, ...] = ()
    adjacency: Mapping[Pair, AdjacencyKind] = field(default_factory=dict[Pair, AdjacencyKind])
    borders: Mapping[Pair, Border] = field(default_factory=dict[Pair, Border])


def owners_of(map_state: MapState) -> dict[TownKey, int]:
    """Town position -> owner for a generated map, whose ``player_towns`` are in player
    order."""
    return {(t.x, t.y, t.level): i for i, t in enumerate(map_state.player_towns)}


def infer_places(
    catalog: Catalog, map_state: MapState, level: int, owners: Mapping[TownKey, int]
) -> InferredPlaces:
    """The places of ``level``, empty when the map has no such level. ``owners`` maps a
    town's ``(x, y, level)`` to its owner, and a town missing from it is unowned."""
    ground = read_ground(catalog, map_state, level)
    return InferredPlaces() if ground is None else read_places(ground, owners)


def boundary(tiles: frozenset[Tile]) -> int:
    """The tiles of ``tiles`` with a 4-neighbour outside it."""
    return sum(
        1
        for x, y in tiles
        if any(n not in tiles for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    )


def _palette(ground: Ground, tiles: frozenset[Tile]) -> dict[Terrain, int]:
    return dict(sorted(collections.Counter(ground.terrain[y][x] for x, y in tiles).items()))


def _role(place: Place, cross: Sequence[Crossing], degree: int, median: float) -> PlaceRole:
    if place.owner is not None:
        return PlaceRole.HOME
    if place.towns:
        return PlaceRole.MIDDLE
    if cross and all(c.guarded for c in cross) and place.rewards > median:
        return PlaceRole.TREASURE
    if len(cross) <= 1 and place.area < POCKET_MAX_AREA:
        return PlaceRole.POCKET
    if 2 * place.area / max(1, place.boundary) < PASS_WIDTH and degree == PASS_DEGREE:
        return PlaceRole.PASS
    return PlaceRole.MIDDLE


def _grid(ground: Ground, labels: Mapping[Tile, int]) -> tuple[tuple[int, ...], ...]:
    return tuple(
        tuple(labels.get((x, y), -1) for x in range(ground.width)) for y in range(ground.height)
    )


def _draft(
    ground: Ground,
    tiles: frozenset[Tile],
    towns: Sequence[tuple[TownKey, Tile]],
    owners: Mapping[TownKey, int],
    rewards: int,
) -> Place:
    owned = [owners[k] for k, _ in towns if k in owners]
    palette = _palette(ground, tiles)
    return Place(
        role=PlaceRole.MIDDLE,
        owner=min(owned) if owned else None,
        area=len(tiles),
        dominant=max(palette, key=lambda t: (palette[t], -t)),
        terrain=palette,
        boundary=boundary(tiles),
        towns=tuple(sorted({a for _, a in towns})),
        rewards=rewards,
    )


def read_places(ground: Ground, owners: Mapping[TownKey, int]) -> InferredPlaces:
    """The places of one level read from its ground."""
    growth = grow_places(ground)
    remap = merge_regions(ground, growth.labels, set(growth.towns))
    labels = {t: remap[lab] for t, lab in growth.labels.items()}
    regions: dict[int, set[Tile]] = collections.defaultdict(set)
    for t, lab in labels.items():
        regions[lab].add(t)
    towns: dict[int, list[tuple[TownKey, Tile]]] = collections.defaultdict(list)
    for seed, keys in growth.towns.items():
        towns[remap[seed]].extend((k, growth.anchors[seed]) for k in keys)
    rewards = collections.Counter(labels[t] for t in ground.rewards if t in labels)
    borders: dict[Pair, Border] = {}
    for pq, edges in border_pairs(labels).items():
        cross = crossings(ground, edges)
        borders[pq] = Border(tuple(edges), cross, adjacency_kind(cross))
    drafts = [
        _draft(ground, frozenset(regions[p]), towns[p], owners, rewards[p])
        for p in range(len(regions))
    ]
    median = statistics.median(rewards[p] for p in range(len(regions))) if regions else 0.0
    places = tuple(_finish(p, d, borders, median) for p, d in enumerate(drafts))
    return InferredPlaces(
        labels=_grid(ground, labels),
        places=places,
        adjacency={pq: b.kind for pq, b in borders.items()},
        borders=borders,
    )


def degree(borders: Mapping[Pair, Border], p: int) -> int:
    """How many places ``p`` borders through a walkable crossing."""
    return sum(1 for pq, b in borders.items() if p in pq and b.kind != AdjacencyKind.CLOSED)


def _finish(p: int, draft: Place, borders: Mapping[Pair, Border], median: float) -> Place:
    cross = [c for pq, b in borders.items() if p in pq for c in b.crossings]
    return Place(
        role=_role(draft, cross, degree(borders, p), median),
        owner=draft.owner,
        area=draft.area,
        dominant=draft.dominant,
        terrain=draft.terrain,
        boundary=draft.boundary,
        towns=draft.towns,
        rewards=draft.rewards,
    )

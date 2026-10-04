"""The road statistics of one level of a corpus or generated map (map-math 3.4, Roads): how
much road it carries, which towns a road reaches and joins, which borders a road crosses,
the surface by hop from home and how closely roads keep to the dominant terrain."""

import collections
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.grid.geometry import NB8
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.priors.places import RoadCount, RoadStats
from vcmi_mapgen.core.reading.borders import AdjacencyKind
from vcmi_mapgen.core.reading.content import UNREACHED, hops
from vcmi_mapgen.core.reading.ground import Ground
from vcmi_mapgen.core.reading.places import InferredPlaces, PlaceRole

TOWN_REACH = 2
NEAR = 2
HOP_CAP = 4


@dataclass(frozen=True, slots=True)
class RoadReading:
    """One level's road statistics, in the shapes ``RoadStats`` pools."""

    count: RoadCount
    crossed: Mapping[str, tuple[int, int]]
    surface: Mapping[int, Mapping[int, int]]
    on_dominant: tuple[int, int]
    land_dominant: tuple[int, int]
    near: tuple[int, int]


def road_components(roads: Iterable[Tile]) -> dict[Tile, int]:
    """Each road tile's 8-connected component id, numbered in sorted tile order."""
    tiles = set(roads)
    comp: dict[Tile, int] = {}
    for start in sorted(tiles):
        if start in comp:
            continue
        cid = len(set(comp.values()))
        comp[start] = cid
        stack = [start]
        while stack:
            x, y = stack.pop()
            for dx, dy in NB8:
                nb = (x + dx, y + dy)
                if nb in tiles and nb not in comp:
                    comp[nb] = cid
                    stack.append(nb)
    return comp


def _near(t: Tile, tiles: Mapping[Tile, int], reach: int) -> set[int]:
    x, y = t
    return {
        tiles[(x + dx, y + dy)]
        for dx in range(-reach, reach + 1)
        for dy in range(-reach, reach + 1)
        if (x + dx, y + dy) in tiles
    }


def town_links(towns: Sequence[Tile], comp: Mapping[Tile, int]) -> tuple[int, int]:
    """(towns with a road tile within ``TOWN_REACH``, towns whose road reaches another
    town)."""
    reached = [_near(t, comp, TOWN_REACH) for t in towns]
    joined = sum(1 for r in reached if r)
    linked = sum(
        1 for i, r in enumerate(reached) if any(r & o for j, o in enumerate(reached) if j != i)
    )
    return joined, linked


def crossed_pairs(labels: Sequence[Sequence[int]], roads: Iterable[Tile]) -> set[tuple[int, int]]:
    """The place pairs ``(a, b)``, ``a < b``, joined by two 8-adjacent road tiles."""
    tiles = set(roads)
    out: set[tuple[int, int]] = set()
    for x, y in tiles:
        a = labels[y][x]
        for dx, dy in NB8:
            nb = (x + dx, y + dy)
            if nb in tiles:
                b = labels[nb[1]][nb[0]]
                if a >= 0 and b >= 0 and a != b:
                    out.add((min(a, b), max(a, b)))
    return out


def read_roads(
    ground: Ground,
    inferred: InferredPlaces,
    roads: Mapping[Tile, int],
    sites: Sequence[Tile] = (),
) -> RoadReading:
    """The road statistics of one level. ``roads`` maps a tile to its road surface and
    ``sites`` holds one tile per object the near share counts."""
    labels, places = inferred.labels, inferred.places
    on_land = {t: r for t, r in roads.items() if t in ground.land}
    comp = road_components(on_land)
    towns = [t for place in places for t in place.towns]
    homes = [t for place in places if place.role == PlaceRole.HOME for t in place.towns]
    joined, linked = town_links(towns, comp)
    home_joined, _ = town_links(homes, comp)
    count = RoadCount(
        len(on_land), len(ground.walk), len(towns), joined, linked, len(homes), home_joined
    )
    crossed = crossed_pairs(labels, on_land)
    tally: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    for (p, q), kind in inferred.adjacency.items():
        a, b = sorted((places[p].role.value, places[q].role.value))
        cell = tally[f"{a}|{b}|{kind.value}"]
        cell[0] += (p, q) in crossed
        cell[1] += 1
    passable = [pq for pq, kind in inferred.adjacency.items() if kind != AdjacencyKind.CLOSED]
    hop = hops(passable, [p for p, place in enumerate(places) if place.role == PlaceRole.HOME])
    surface: dict[int, collections.Counter[int]] = collections.defaultdict(collections.Counter)
    on = 0
    for (x, y), r in on_land.items():
        p = labels[y][x]
        surface[min(hop.get(p, UNREACHED), HOP_CAP)][r] += 1
        on += p >= 0 and ground.terrain[y][x] == places[p].dominant
    land_on = sum(place.terrain[place.dominant] for place in places)
    near_sites = sum(1 for s in sites if _near(s, comp, NEAR))
    return RoadReading(
        count=count,
        crossed={k: (v[0], v[1]) for k, v in tally.items()},
        surface={h: dict(c) for h, c in surface.items()},
        on_dominant=(on, len(on_land)),
        land_dominant=(land_on, sum(place.area for place in places)),
        near=(near_sites, len(sites)),
    )


def pool_roads(readings: Iterable[RoadReading]) -> RoadStats:
    """The corpus road statistics pooled over every level's reading. ``crossed`` pools only
    the levels that carry a road, so it reads as the crossing rate given a road network."""
    counts: list[RoadCount] = []
    crossed: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    surface: dict[int, collections.Counter[int]] = collections.defaultdict(collections.Counter)
    sums = [0] * 6
    for r in readings:
        counts.append(r.count)
        if not r.count.road:
            continue
        for k, (hit, total) in r.crossed.items():
            crossed[k][0] += hit
            crossed[k][1] += total
        for h, c in r.surface.items():
            surface[h].update(c)
        for i, v in enumerate((*r.on_dominant, *r.land_dominant, *r.near)):
            sums[i] += v
    return RoadStats(
        counts=tuple(counts),
        crossed={k: (v[0], v[1]) for k, v in sorted(crossed.items())},
        surface={h: dict(sorted(c.items())) for h, c in sorted(surface.items())},
        on_dominant=(sums[0], sums[1]),
        land_dominant=(sums[2], sums[3]),
        near=(sums[4], sums[5]),
    )

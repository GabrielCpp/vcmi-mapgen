"""Mine the place statistics of one level: infer the places of every corpus map and pool
their counts, sizes, adjacencies, shapes, palettes and borders (map-math 3.4)."""

import collections
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.priors.places import PaletteCount, PlaceContent, PlaceCount, PlaceStats
from vcmi_mapgen.core.reading.borders import AdjacencyKind
from vcmi_mapgen.core.reading.content import hops, place_content
from vcmi_mapgen.core.reading.ground import Ground, TownKey, read_ground
from vcmi_mapgen.core.reading.measures import (
    BorderKind,
    barrier_depth,
    border_kind,
    compactness,
    home_separation,
    raw_cut_share,
    regions,
    roughness,
    soft_borders,
)
from vcmi_mapgen.core.reading.paint import accents
from vcmi_mapgen.core.reading.palette import palette_regions, same_by_roles
from vcmi_mapgen.core.reading.places import InferredPlaces, PlaceRole, degree, read_places
from vcmi_mapgen.core.reading.roads import RoadReading, pool_roads, read_roads
from vcmi_mapgen.vcmi.formats import h3m

TOWN_CLASSES = frozenset({77, 98})
NEUTRAL = 255


@dataclass(frozen=True, slots=True)
class MapPlayers:
    """A corpus map's playable player count and each owned town's owner, read from its
    ``.h3m``, because the corpus ``.vmap`` files carry no owner."""

    players: int
    owners: Mapping[TownKey, int]


def map_players(h3m_dir: Path, name: str) -> MapPlayers:
    m = h3m.parse_file(str(h3m_dir / f"{name}.h3m"))
    owners = {
        (o.x, o.y, o.level): o.extra["owner"]
        for o in m.objects
        if o.obj_class in TOWN_CLASSES and o.extra.get("owner", NEUTRAL) != NEUTRAL
    }
    return MapPlayers(m.players, owners)


def _floats() -> collections.defaultdict[str, list[float]]:
    return collections.defaultdict(list)


@dataclass(slots=True)
class _Pool:
    counts: list[PlaceCount] = field(default_factory=list[PlaceCount])
    rel_size: collections.defaultdict[str, list[float]] = field(default_factory=_floats)
    adjacency: collections.Counter[str] = field(default_factory=collections.Counter[str])
    degree: collections.defaultdict[str, list[int]] = field(
        default_factory=lambda: collections.defaultdict(list)
    )
    home_separation: list[float] = field(default_factory=list[float])
    compactness: collections.defaultdict[str, list[float]] = field(default_factory=_floats)
    roughness: collections.defaultdict[str, list[float]] = field(default_factory=_floats)
    dominant: collections.defaultdict[str, collections.Counter[int]] = field(
        default_factory=lambda: collections.defaultdict(collections.Counter)
    )
    dominant_share: collections.defaultdict[str, list[float]] = field(default_factory=_floats)
    border_kinds: collections.Counter[str] = field(default_factory=collections.Counter[str])
    barrier_depth: list[float] = field(default_factory=list[float])
    accent_rate: collections.defaultdict[int, list[float]] = field(
        default_factory=lambda: collections.defaultdict(list)
    )
    accent_size: collections.defaultdict[int, list[int]] = field(
        default_factory=lambda: collections.defaultdict(list)
    )
    transition_width: list[int] = field(default_factory=list[int])
    raw_cut: list[float] = field(default_factory=list[float])
    palette_counts: list[PaletteCount] = field(default_factory=list[PaletteCount])
    same_by_roles: collections.defaultdict[str, list[int]] = field(
        default_factory=lambda: collections.defaultdict(lambda: [0, 0])
    )
    content: list[PlaceContent] = field(default_factory=list[PlaceContent])
    roads: list[RoadReading] = field(default_factory=list[RoadReading])

    def add(self, ground: Ground, inferred: InferredPlaces, players: int) -> None:
        land = len(ground.land)
        self.counts.append(PlaceCount(len(inferred.places), players, land))
        self.home_separation.extend(home_separation(ground, inferred))
        tiles = regions(inferred)
        for p, place in enumerate(inferred.places):
            role = place.role.value
            self.rel_size[role].append(place.area / land)
            self.degree[role].append(degree(inferred.borders, p))
            self.compactness[role].append(compactness(place))
            self.roughness[role].append(roughness(place, tiles[p]))
            self.dominant[role][int(place.dominant)] += 1
            self.dominant_share[role].append(place.terrain[place.dominant] / place.area)
        self._add_borders(ground, inferred, tiles)
        self._add_paint(ground, inferred)
        self._add_palette(inferred, land)

    def add_content(
        self, catalog: Catalog, state: MapState, level: int, inferred: InferredPlaces
    ) -> None:
        homes = [p for p, place in enumerate(inferred.places) if place.role == PlaceRole.HOME]
        if not homes:
            return
        walk = [pq for pq, kind in inferred.adjacency.items() if kind != AdjacencyKind.CLOSED]
        roles = {p: place.role.value for p, place in enumerate(inferred.places)}
        objs = state.objs_by_level([level])[level]
        self.content.extend(place_content(catalog, objs, inferred.labels, roles, hops(walk, homes)))

    def add_roads(
        self, ground: Ground, inferred: InferredPlaces, roads: Mapping[tuple[int, int], int]
    ) -> None:
        self.roads.append(read_roads(ground, inferred, roads, ground.rewards))

    def _add_palette(self, inferred: InferredPlaces, land: int) -> None:
        dominant = {p: int(place.dominant) for p, place in enumerate(inferred.places)}
        roles = {p: place.role.value for p, place in enumerate(inferred.places)}
        pairs = list(inferred.borders)
        count = PaletteCount(palette_regions(dominant, pairs), len(inferred.places), land)
        self.palette_counts.append(count)
        for key, (same, total) in same_by_roles(roles, dominant, pairs).items():
            tally = self.same_by_roles[key]
            tally[0] += same
            tally[1] += total

    def _add_borders(
        self,
        ground: Ground,
        inferred: InferredPlaces,
        tiles: Mapping[int, frozenset[tuple[int, int]]],
    ) -> None:
        for (p, q), border in inferred.borders.items():
            a, b = sorted((inferred.places[p].role.value, inferred.places[q].role.value))
            self.adjacency[f"{a}|{b}|{border.kind.value}"] += 1
            same = "same" if inferred.places[p].dominant == inferred.places[q].dominant else "diff"
            kind = border_kind(ground, border.edges)
            self.border_kinds[f"{border.kind.value}|{same}|{kind.value}"] += 1
            if kind == BorderKind.BARRIER:
                self.barrier_depth.append(barrier_depth(ground, border, tiles[p] | tiles[q]))

    def _add_paint(self, ground: Ground, inferred: InferredPlaces) -> None:
        label = inferred.labels
        dominant = {p: place.dominant for p, place in enumerate(inferred.places)}
        found = accents(ground.terrain, label, dominant)
        per_place = collections.Counter(a.place for a in found)
        for p, place in enumerate(inferred.places):
            self.accent_rate[int(place.dominant)].append(100 * per_place[p] / place.area)
        for a in found:
            self.accent_size[int(dominant[a.place])].append(a.size)
        soft = soft_borders(ground, inferred)
        self.transition_width.extend(soft.widths.values())
        share = raw_cut_share(ground, inferred, soft)
        if share is not None:
            self.raw_cut.append(share)

    def stats(self) -> PlaceStats:
        return PlaceStats(
            counts=tuple(self.counts),
            rel_size={k: tuple(v) for k, v in sorted(self.rel_size.items())},
            adjacency=dict(sorted(self.adjacency.items())),
            degree={k: tuple(v) for k, v in sorted(self.degree.items())},
            home_separation=tuple(self.home_separation),
            compactness={k: tuple(v) for k, v in sorted(self.compactness.items())},
            roughness={k: tuple(v) for k, v in sorted(self.roughness.items())},
            dominant={k: dict(sorted(v.items())) for k, v in sorted(self.dominant.items())},
            dominant_share={k: tuple(v) for k, v in sorted(self.dominant_share.items())},
            border_kinds=dict(sorted(self.border_kinds.items())),
            barrier_depth=tuple(self.barrier_depth),
            accent_rate={k: tuple(v) for k, v in sorted(self.accent_rate.items())},
            accent_size={k: tuple(v) for k, v in sorted(self.accent_size.items())},
            transition_width=tuple(self.transition_width),
            raw_cut=tuple(self.raw_cut),
            palette_counts=tuple(self.palette_counts),
            same_by_roles={k: (v[0], v[1]) for k, v in sorted(self.same_by_roles.items())},
            content=tuple(self.content),
            roads=pool_roads(self.roads),
        )


def mine_places(
    catalog: Catalog, level: int, maps: Sequence[MapState], players: Sequence[MapPlayers]
) -> PlaceStats:
    """The place statistics of ``level`` over ``maps``, each paired with its players."""
    pool = _Pool()
    for state, mp in zip(maps, players, strict=True):
        ground = read_ground(catalog, state, level)
        if ground is None or not ground.land:
            continue
        inferred = read_places(ground, mp.owners)
        pool.add(ground, inferred, mp.players)
        pool.add_content(catalog, state, level, inferred)
        pool.add_roads(ground, inferred, state.roads.get(level, {}))
    return pool.stats()


def place_labels(
    catalog: Catalog, level: int, maps: Sequence[MapState]
) -> list[tuple[tuple[int, ...], ...]]:
    """Each map's inferred place label grid of ``level``, empty when it has no land there.
    Ownership changes roles only, so no owner is read."""
    out: list[tuple[tuple[int, ...], ...]] = []
    for state in maps:
        ground = read_ground(catalog, state, level)
        out.append(read_places(ground, {}).labels if ground is not None and ground.land else ())
    return out

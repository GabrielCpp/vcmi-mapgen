"""Territories on one level of a corpus or generated map: the stretches of land a hero
crosses without a fight, the guards and gates between them, and the places each holds.

A monster takes its visit tile and the eight around it out of the land, and a gate or a
quest guard takes its visit tile. What land stays walkable splits into 8-connected
stretches, and a stretch under ``MIN_AREA`` tiles is no territory. A territory belongs to
the players whose home town stands on its edge, and to no one otherwise. A door is a run of
barriers, with the fragments between them, that touches two or more territories. A
teleport, a one-way monolith or a subterranean gate links two territories and splits none.
"""

from __future__ import annotations

import collections
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from vcmi_mapgen.core.catalog import Catalog, Crossing
from vcmi_mapgen.core.grid.splits import MIN_AREA
from vcmi_mapgen.core.model import MapState, PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.reading.ground import TownKey, purpose_of, read_ground
from vcmi_mapgen.core.reading.places import read_places
from vcmi_mapgen.core.reading.routes import RouteMap, route_map

NONE = -1

type Grid = tuple[tuple[int, ...], ...]
type Pair = tuple[int, int]

_N8 = tuple((dx, dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dx or dy)


class BarrierKind(StrEnum):
    GUARD = "guard"
    GATE = "gate"


@dataclass(frozen=True, slots=True)
class Barrier:
    """One monster or gate a hero beats or opens to pass: its kind, its anchor, its
    creature level, None for a gate or a monster of any level, and the walkable land tiles
    it takes out of every territory."""

    kind: BarrierKind
    anchor: Tile
    level: int | None
    tiles: frozenset[Tile]


@dataclass(frozen=True, slots=True)
class Door:
    """A run of barriers, with the fragments between them, that touches two or more
    territories. ``territories`` holds their sorted ids and ``tiles`` the run's tiles."""

    territories: tuple[int, ...]
    barriers: tuple[Barrier, ...]
    tiles: frozenset[Tile]

    @property
    def level(self) -> int | None:
        """The strongest known creature level in the run, None when it holds no monster of a
        known level."""
        levels = [b.level for b in self.barriers if b.level is not None]
        return max(levels) if levels else None

    @property
    def gated(self) -> bool:
        return any(b.kind is BarrierKind.GATE for b in self.barriers)

    def pairs(self) -> list[Pair]:
        """Every pair of territories the door joins."""
        ids = self.territories
        return [(a, b) for i, a in enumerate(ids) for b in ids[i + 1 :]]


@dataclass(frozen=True, slots=True)
class Territory:
    """One territory: the players whose home town stands on its edge, empty when it is
    neutral, its tile count, the places whose tiles mostly lie in it, and how many towns of
    any owner stand on its edge."""

    owners: tuple[int, ...]
    area: int
    zones: tuple[int, ...]
    towns: int

    @property
    def neutral(self) -> bool:
        return not self.owners


@dataclass(frozen=True, slots=True)
class Territories:
    """The territories of one level. ``labels[y][x]`` is the territory id of a tile and
    ``NONE`` elsewhere. ``links`` holds each sorted territory pair a jump on this level
    joins."""

    level: int
    labels: Grid
    territories: tuple[Territory, ...]
    barriers: tuple[Barrier, ...]
    doors: tuple[Door, ...]
    links: tuple[Pair, ...]

    def pairs(self) -> dict[Pair, list[Door]]:
        """The doors between each bordering pair of territories."""
        out: dict[Pair, list[Door]] = {}
        for door in self.doors:
            for pair in door.pairs():
                out.setdefault(pair, []).append(door)
        return dict(sorted(out.items()))

    def at(self, t: Tile) -> int:
        x, y = t
        return (
            self.labels[y][x]
            if 0 <= y < len(self.labels) and 0 <= x < len(self.labels[y])
            else NONE
        )


@dataclass(frozen=True, slots=True)
class PlannedTopology:
    """The territories a generator planned for one level: ``labels[y][x]`` is the planned
    territory id of a tile and ``NONE`` elsewhere, ``owners`` gives each planned territory's
    players, and ``doors`` holds the tile of each planned door."""

    labels: Grid
    owners: tuple[tuple[int, ...], ...]
    doors: tuple[Tile, ...]


def _visits(obj: PlacedObject) -> list[Tile]:
    cells = [t for t, role in obj.footprint.at(obj.x, obj.y) if role.interactive]
    return cells or [(obj.x, obj.y)]


def _walkable(route: RouteMap, level: int) -> frozenset[Tile]:
    open_, water = route.open[level], route.water[level]
    return frozenset(
        (x, y) for y, row in enumerate(open_) for x, ok in enumerate(row) if ok and not water[y][x]
    )


def _water(route: RouteMap, level: int) -> frozenset[Tile]:
    return frozenset(
        (x, y) for y, row in enumerate(route.water[level]) for x, wet in enumerate(row) if wet
    )


def _barrier(
    catalog: Catalog, obj: PlacedObject, walk: frozenset[Tile], water: frozenset[Tile]
) -> Barrier | None:
    purpose = purpose_of(catalog, obj)
    crossing = catalog.crossing(obj.kind)
    visits = _visits(obj)
    if purpose == Purpose.GUARD:
        ashore = [t for t in visits if t not in water]
        ring = {(x + dx, y + dy) for x, y in ashore for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
        level = catalog.creature_level(obj.kind)
        return Barrier(BarrierKind.GUARD, (obj.x, obj.y), level, frozenset(ring & walk))
    gate = crossing is not None and crossing[0] is Crossing.GATE
    if gate or (purpose == Purpose.QUEST_GATE and catalog.is_vanish(obj.kind)):
        return Barrier(BarrierKind.GATE, (obj.x, obj.y), None, frozenset(set(visits) & walk))
    return None


def barriers_of(
    catalog: Catalog,
    objs: Sequence[PlacedObject],
    walk: frozenset[Tile],
    water: frozenset[Tile],
) -> tuple[Barrier, ...]:
    """Every monster and gate among ``objs`` whose barrier takes at least one tile of
    ``walk``. A monster afloat on ``water`` holds no land."""
    found = (_barrier(catalog, o, walk, water) for o in objs)
    return tuple(b for b in found if b is not None and b.tiles)


def _components(tiles: frozenset[Tile]) -> list[list[Tile]]:
    seen: set[Tile] = set()
    out: list[list[Tile]] = []
    for start in sorted(tiles, key=lambda t: (t[1], t[0])):
        if start in seen:
            continue
        seen.add(start)
        comp, queue = [start], collections.deque([start])
        while queue:
            x, y = queue.popleft()
            for dx, dy in _N8:
                n = (x + dx, y + dy)
                if n in tiles and n not in seen:
                    seen.add(n)
                    comp.append(n)
                    queue.append(n)
        out.append(comp)
    return out


def _touching(label: Mapping[Tile, int], tiles: Sequence[Tile]) -> set[int]:
    return {
        t
        for x, y in tiles
        for dx, dy in ((0, 0), *_N8)
        if (t := label.get((x + dx, y + dy), NONE)) != NONE
    }


def _doors(
    barriers: Sequence[Barrier], fragments: frozenset[Tile], label: Mapping[Tile, int]
) -> tuple[Door, ...]:
    held = frozenset(t for b in barriers for t in b.tiles)
    doors: list[Door] = []
    for comp in _components(held | fragments):
        tiles = frozenset(comp)
        if not tiles & held:
            continue
        touched = _touching(label, comp)
        if len(touched) < 2:
            continue
        run = tuple(b for b in barriers if b.tiles & tiles)
        doors.append(Door(tuple(sorted(touched)), run, tiles))
    return tuple(doors)


def _zones(places: Grid, label: Mapping[Tile, int]) -> dict[int, list[int]]:
    share: dict[int, collections.Counter[int]] = collections.defaultdict(collections.Counter)
    for t, terr in label.items():
        p = places[t[1]][t[0]] if places else NONE
        if p != NONE:
            share[p][terr] += 1
    out: dict[int, list[int]] = collections.defaultdict(list)
    for p, counts in sorted(share.items()):
        out[max(counts, key=lambda terr: (counts[terr], -terr))].append(p)
    return out


def _towns(
    catalog: Catalog,
    objs: Sequence[PlacedObject],
    owners: Mapping[TownKey, int],
    label: Mapping[Tile, int],
) -> tuple[dict[int, set[int]], collections.Counter[int]]:
    owned: dict[int, set[int]] = collections.defaultdict(set)
    towns: collections.Counter[int] = collections.Counter()
    for o in objs:
        if purpose_of(catalog, o) != Purpose.TOWN:
            continue
        owner = owners.get((o.x, o.y, o.level))
        for terr in _touching(label, _visits(o)):
            towns[terr] += 1
            if owner is not None:
                owned[terr].add(owner)
    return owned, towns


def _links(route: RouteMap, level: int, label: Mapping[Tile, int]) -> tuple[Pair, ...]:
    pairs: set[Pair] = set()
    for spot, landing in route.jumps.items():
        if spot.level != level:
            continue
        here = _touching(label, [(spot.x, spot.y)])
        there = _touching(label, [(s.x, s.y) for s in landing if s.level == level])
        pairs.update((min(a, b), max(a, b)) for a in here for b in there if a != b)
    return tuple(sorted(pairs))


def territories_from(
    catalog: Catalog,
    map_state: MapState,
    route: RouteMap,
    level: int,
    owners: Mapping[TownKey, int],
) -> Territories | None:
    """The territories of ``level`` read over ``route``, or None when the map has no such
    level. Each inferred place goes to the territory that holds most of its tiles, and
    ``owners`` maps a town's ``(x, y, level)`` to its owner."""
    ground = read_ground(catalog, map_state, level)
    if ground is None:
        return None
    places = read_places(ground, owners).labels
    size = map_state.size
    walk = _walkable(route, level)
    objs = map_state.objs_by_level([level])[level]
    barriers = barriers_of(catalog, objs, walk, _water(route, level))
    held = frozenset(t for b in barriers for t in b.tiles)
    stretches = sorted(_components(walk - held), key=lambda c: (-len(c), c[0][1], c[0][0]))
    big = [c for c in stretches if len(c) >= MIN_AREA]
    label = {t: i for i, c in enumerate(big) for t in c}
    fragments = frozenset(t for c in stretches if len(c) < MIN_AREA for t in c)
    owned, towns = _towns(catalog, objs, owners, label)
    zones = _zones(places, label)
    territories = tuple(
        Territory(tuple(sorted(owned[i])), len(c), tuple(zones[i]), towns[i])
        for i, c in enumerate(big)
    )
    grid = tuple(tuple(label.get((x, y), NONE) for x in range(size)) for y in range(size))
    return Territories(
        level=level,
        labels=grid,
        territories=territories,
        barriers=barriers,
        doors=_doors(barriers, fragments, label),
        links=_links(route, level, label),
    )


def islands(read: Territories, water: Sequence[Sequence[bool]]) -> list[int]:
    """The territories with no door whose land, every tile off ``water`` they reach over
    the eight neighbours, holds no other territory."""
    land = frozenset((x, y) for y, row in enumerate(water) for x, wet in enumerate(row) if not wet)
    held: dict[int, set[int]] = collections.defaultdict(set)
    for mass in _components(land):
        found = {read.at(t) for t in mass} - {NONE}
        for t in found:
            held[t] = found
    opened = {t for d in read.doors for t in d.territories}
    return [t for t in range(len(read.territories)) if t not in opened and held[t] == {t}]


def read_territories(
    catalog: Catalog, map_state: MapState, level: int, owners: Mapping[TownKey, int]
) -> Territories | None:
    """The territories of ``level``, or None when the map has no such level."""
    return territories_from(catalog, map_state, route_map(catalog, map_state), level, owners)


@dataclass(frozen=True, slots=True)
class TerritoryReading:
    """One level's territory spread: the zones of each player and each neutral territory,
    the doors between each bordering pair, and the known level of each door out of a player
    territory and each door between neutral territories."""

    player_zones: tuple[int, ...]
    neutral_zones: tuple[int, ...]
    pair_doors: tuple[int, ...]
    player_door_levels: tuple[int, ...]
    neutral_door_levels: tuple[int, ...]


def territory_reading(read: Territories) -> TerritoryReading:
    """The spread ``read`` gives."""
    terrs = read.territories
    player: list[int] = []
    neutral: list[int] = []
    for door in read.doors:
        level = door.level
        if level is None:
            continue
        if any(not terrs[i].neutral for i in door.territories):
            player.append(level)
        else:
            neutral.append(level)
    return TerritoryReading(
        player_zones=tuple(len(t.zones) for t in terrs if not t.neutral),
        neutral_zones=tuple(len(t.zones) for t in terrs if t.neutral),
        pair_doors=tuple(len(d) for d in read.pairs().values()),
        player_door_levels=tuple(player),
        neutral_door_levels=tuple(neutral),
    )


def disagreements(planned: PlannedTopology, read: Territories) -> list[str]:
    """Where the read territories part from the planned ones: a read territory that spans
    two planned ones, a planned territory split over two read ones, a read territory whose
    owners differ from its planned territory's, and a planned door no read door holds."""
    cover: dict[int, collections.Counter[int]] = collections.defaultdict(collections.Counter)
    for y, row in enumerate(read.labels):
        for x, r in enumerate(row):
            p = planned.labels[y][x] if y < len(planned.labels) else NONE
            if NONE not in (r, p):
                cover[r][p] += 1
    out: list[str] = []
    split: dict[int, list[int]] = collections.defaultdict(list)
    for r, counts in sorted(cover.items()):
        if len(counts) > 1:
            names = ", ".join(f"planned {p}" for p in sorted(counts))
            out.append(f"read {r} spans {names}")
        main = max(counts, key=lambda p: (counts[p], -p))
        split[main].append(r)
        if main < len(planned.owners) and planned.owners[main] != read.territories[r].owners:
            out.append(
                f"read {r} owners {list(read.territories[r].owners)}, "
                + f"planned {main} owners {list(planned.owners[main])}"
            )
    out += [
        f"planned {p} splits into read {', '.join(map(str, rs))}"
        for p, rs in sorted(split.items())
        if len(rs) > 1
    ]
    held = frozenset(t for d in read.doors for t in d.tiles)
    out += [
        f"planned door at {x},{y} reads no door" for x, y in planned.doors if (x, y) not in held
    ]
    return out

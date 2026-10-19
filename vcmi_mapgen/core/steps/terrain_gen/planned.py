"""The planned territory front: one corpus map's arrangement of territories is stretched
onto the land, each territory floods from its site to its share by a quota flood, and
each territory is then cut into places of its own."""

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

import numpy as np

from vcmi_mapgen.core.grid.noise import value_noise
from vcmi_mapgen.core.grid.quota import (
    Field,
    Labels,
    Mask,
    cell_areas,
    cell_tiles,
    quota_flood,
)
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.priors.places import PlaceStats
from vcmi_mapgen.core.priors.territories import TerritoryPlan, TerritoryStats
from vcmi_mapgen.core.steps.terrain_gen.homes import Homes, room_side, room_tiles
from vcmi_mapgen.core.steps.terrain_gen.layout import Land, Layout, home_gap
from vcmi_mapgen.core.steps.terrain_gen.model import FrontDraw, TerrainOptions
from vcmi_mapgen.core.steps.terrain_gen.place_draws import NEAREST_RECORDS
from vcmi_mapgen.core.steps.terrain_gen.place_map import label_adjacency
from vcmi_mapgen.core.steps.terrain_gen.shapes import grow_shapes, shape_caps
from vcmi_mapgen.core.steps.terrain_gen.streams import stream
from vcmi_mapgen.core.steps.terrain_gen.territories import settle

JITTER = 0.03
NOISE_CELLS = 6
type Point = tuple[float, float]


@dataclass(frozen=True, slots=True)
class Site:
    """One territory of the plan on this map: the unit-square ``point`` it sits at, its
    ``share`` of the land and its player, None when neutral."""

    point: Point
    share: float
    owner: int | None


def choose_plan(
    plans: Sequence[TerritoryPlan], players: int, land: int, rng: random.Random
) -> TerritoryPlan:
    """One corpus plan with exactly ``players`` player territories, drawn among the
    ``NEAREST_RECORDS`` whose land is closest to ``land``. It raises ``ValueError`` when
    the corpus holds no such plan."""
    fit = [p for p in plans if len({s.owner for s in p.sites if s.owner is not None}) == players]
    if not fit:
        raise ValueError(f"no corpus territory plan seats {players} players")
    fit.sort(key=lambda p: (abs(math.log(max(1, p.record.land) / max(1, land))), p.record.land))
    return rng.choice(fit[:NEAREST_RECORDS])


def symmetric(point: Point, which: int) -> Point:
    """``point`` under one of the 8 symmetries of the unit square: bit 0 mirrors x, bit 1
    mirrors y and bit 2 swaps the axes first."""
    x, y = point
    if which & 4:
        x, y = y, x
    if which & 1:
        x = 1 - x
    if which & 2:
        y = 1 - y
    return x, y


def plan_sites(plan: TerritoryPlan, players: int, seed: int) -> list[Site]:
    """The sites of ``plan`` under a drawn symmetry and jitter, with the players dealt
    onto its owned sites in a drawn order. A corpus player that holds several territories
    keeps its largest as home, and the others turn neutral."""
    which = stream(seed, "plan_symmetry").randrange(8)
    jitter = stream(seed, "plan_jitter")
    seats = list(range(players))
    stream(seed, "plan_seats").shuffle(seats)
    homes: dict[int, int] = {}
    for i, s in enumerate(plan.sites):
        if s.owner is not None and (
            s.owner not in homes or s.share > plan.sites[homes[s.owner]].share
        ):
            homes[s.owner] = i
    owned = iter(seats)
    seat = {i: next(owned) for i in sorted(homes.values())}
    out: list[Site] = []
    for i, s in enumerate(plan.sites):
        x, y = symmetric((s.x, s.y), which)
        x = min(1.0, max(0.0, x + jitter.uniform(-JITTER, JITTER)))
        y = min(1.0, max(0.0, y + jitter.uniform(-JITTER, JITTER)))
        out.append(Site((x, y), s.share, seat.get(i)))
    return out


def snap_sites(land: Land, points: Sequence[Point]) -> list[Tile]:
    """The land tile nearest each point of the unit square, each tile taken once: a site
    whose tile is taken goes to the nearest free land tile."""
    side = len(land)
    free = [(x, y) for y, row in enumerate(land) for x, v in enumerate(row) if v]
    out: list[Tile] = []
    for px, py in points:
        tile = min(free, key=lambda t: ((t[0] - px * side) ** 2 + (t[1] - py * side) ** 2, t))
        free.remove(tile)
        out.append(tile)
    return out


def noise_fields(count: int, side: int, seed: int) -> list[Field]:
    """One border noise field per territory, in [-1, 1], with a wavelength of a sixth of
    the side."""
    cell = max(2, side // NOISE_CELLS)
    return [
        np.asarray(value_noise(side, side, cell, stream(seed, "plan_noise", i)), dtype=np.float64)
        for i in range(count)
    ]


def partition(land: Mask, sites: Sequence[Site], seed: int) -> tuple[Labels, list[Tile], float]:
    """The territory of each land tile, the snapped tile of each site, and the worst area
    error over the targets."""
    side = land.shape[0]
    total = np.count_nonzero(land)
    tiles = snap_sites(cast("Land", land.tolist()), [s.point for s in sites])
    targets = [s.share * total for s in sites]
    label = quota_flood(land, tiles, targets, noise_fields(len(sites), side, seed))
    area = cast("list[float]", cell_areas(label, len(sites)).tolist())
    worst = max(abs(a - t) / t for a, t in zip(area, targets, strict=True) if t > 0)
    return label, tiles, worst


def cut_caps(caps: Sequence[int], area: int, land: int, start: int) -> tuple[list[int], int]:
    """The caps one territory of ``area`` tiles grows its places to, and where the next
    territory resumes in ``caps``. It takes ``round(len(caps) * area / land)`` caps, at
    least one, in order and from the start again when they run out, rescaled to sum to
    ``area``."""
    k = max(1, round(len(caps) * area / land))
    taken = [caps[(start + j) % len(caps)] for j in range(k)]
    scaled = [max(1, round(c * area / sum(taken))) for c in taken]
    scaled[scaled.index(max(scaled))] += area - sum(scaled)
    return scaled, (start + k) % len(caps)


def grow_territories(
    label: Labels, count: int, caps: Sequence[int], seed: int
) -> tuple[Layout, tuple[int, ...]]:
    """One layout over the ``count`` territories of ``label``, each grown on its own mask
    so no place straddles two, and the territory of each place. The places grown from
    anchors come first, in territory order, and the pockets after them."""
    rows = cast("list[list[int]]", label.tolist())
    land = sum(1 for row in rows for c in row if c >= 0)
    anchored: list[tuple[int, int]] = []
    pockets: list[tuple[int, int]] = []
    anchors: list[Tile] = []
    grown: list[Layout] = []
    start = 0
    for t in range(count):
        mask = [[c == t for c in row] for row in rows]
        area = sum(v for row in mask for v in row)
        part, start = cut_caps(caps, area, land, start)
        layout = grow_shapes(mask, part, stream(seed, "layout", t))
        grown.append(layout)
        anchors.extend(layout.anchors)
        for p in range(layout.places):
            (anchored if p < len(layout.anchors) else pockets).append((t, p))
    order = {place: i for i, place in enumerate(anchored + pockets)}
    merged = [[-1] * len(row) for row in rows]
    for t, layout in enumerate(grown):
        for y, row in enumerate(layout.label):
            for x, p in enumerate(row):
                if p >= 0:
                    merged[y][x] = order[(t, p)]
    territory = tuple(t for t, _ in anchored + pockets)
    return Layout(merged, tuple(anchors), len(order)), territory


def home_seat(label: Labels, cell: int, site: Tile) -> Tile:
    """The tile of territory ``cell`` nearest ``site`` whose town room lies wholly inside
    it, else the tile with the most room tiles inside."""
    own = set(cell_tiles(label, cell))
    room = room_tiles((0, 0), room_side())

    def inside(t: Tile) -> int:
        return sum((t[0] + dx, t[1] + dy) in own for dx, dy in room)

    def near(t: Tile) -> tuple[int, Tile]:
        return (t[0] - site[0]) ** 2 + (t[1] - site[1]) ** 2, t

    best = max(inside(t) for t in own)
    return min((t for t in own if inside(t) == best), key=near)


def seat_homes(
    layout: Layout, label: Labels, seats: Sequence[tuple[int, Tile]]
) -> tuple[Homes, list[int | None]]:
    """The homes of the players, one per ``(territory, site)`` of ``seats`` in player
    order, and each place's player."""
    points = tuple(home_seat(label, cell, site) for cell, site in seats)
    places = tuple(layout.label[y][x] for x, y in points)
    neighbours: dict[int, set[int]] = {p: set() for p in range(layout.places)}
    for a, b in label_adjacency(layout.label):
        neighbours[a].add(b)
        neighbours[b].add(a)
    crowded = sum(
        b in neighbours[a] or bool(neighbours[a] & neighbours[b])
        for i, a in enumerate(places)
        for b in places[i + 1 :]
    )
    gap = home_gap([[z >= 0 for z in row] for row in layout.label], points)
    owners: list[int | None] = [None] * layout.places
    for player, place in enumerate(places):
        owners[place] = player
    return Homes(places, points, gap, crowded), owners


class PlannedFront:
    """Territories first: one corpus plan near the player count and land is stretched onto
    the land, a power partition fills it, and each territory is cut into places."""

    def draw(
        self,
        land: Land,
        priors: tuple[PlaceStats, TerritoryStats],
        planned: int,
        seed: int,
        options: TerrainOptions,
    ) -> FrontDraw:
        stats, spread = priors
        mask = np.array(land, dtype=np.bool_)
        tiles = np.count_nonzero(mask)
        plan = choose_plan(spread.plans_by_map, options.players, tiles, stream(seed, "plan"))
        sites = plan_sites(plan, options.players, seed)
        label, snapped, worst = partition(mask, sites, seed)
        count = len(sites)
        caps = shape_caps(stats, options.players, (planned, tiles), stream(seed, "places"))
        layout, drawn = grow_territories(label, count, caps, seed)
        seated = sorted((s.owner, i) for i, s in enumerate(sites) if s.owner is not None)
        homes, owners = seat_homes(layout, label, [(i, snapped[i]) for _, i in seated])
        territory, _ = settle(drawn, owners, label_adjacency(layout.label))
        line = (
            f"  planned front: plan of {options.players}p/{plan.record.land} land, "
            + f"{len(sites)} territories, worst area error {worst:.0%}"
        )
        return FrontDraw(layout, homes, territory, owners, plan.record, len(caps), (line,))

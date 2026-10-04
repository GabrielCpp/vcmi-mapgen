"""Paint (map-math 4.6): grade a transition band across every border between two places of
different dominant terrain, grow accent patches inside each place, texture each place's
interior with the corpus tables counted inside places, and erode what the tiler cannot
draw. The place map never changes, and every draw comes from a named stream."""

import collections
import math
import random
import statistics
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.grid.reach import STEPS4
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.priors.markov import MarkovTables
from vcmi_mapgen.core.priors.places import PlaceStats
from vcmi_mapgen.core.reading.borders import Pair
from vcmi_mapgen.core.reading.paint import (
    border_depth,
    boundary_tiles,
    components,
    half_depth,
    off_dominant,
    pair,
)
from vcmi_mapgen.core.steps.terrain_gen.despeckle import despeckle
from vcmi_mapgen.core.steps.terrain_gen.place_map import label_adjacency
from vcmi_mapgen.core.steps.terrain_gen.result import LevelPlaces
from vcmi_mapgen.core.steps.terrain_gen.streams import stream
from vcmi_mapgen.core.steps.terrain_gen.texture import sample

THETA_QUANTILE = 10
MIN_SAMPLES = 30
MAX_HALF_DEPTH = 3
SWEEPS = 3
MIN_CONTEXT = 10
SMOOTH_VOTES = 3
MAX_RESTORE_ROUNDS = 4
LAND = tuple(t for t in Terrain if t.is_land)

type Work = list[list[int]]
type Labels = Sequence[Sequence[int]]


@dataclass(frozen=True, slots=True)
class PaintPriors:
    """What Paint draws from: the lowest dominant share a place keeps, the corpus transition
    widths, the accent rate per 100 tiles and the accent sizes per dominant terrain, and
    the 4-neighbour tables counted inside places."""

    theta_min: float
    widths: tuple[int, ...]
    accent_rate: Mapping[Terrain, float]
    accent_size: Mapping[Terrain, tuple[int, ...]]
    tables: MarkovTables


@dataclass(frozen=True, slots=True)
class Painted:
    """The painted grid and its transition band tiles."""

    grid: list[list[Terrain]]
    bands: frozenset[Tile]


class Budget:
    """How many more tiles of each place may leave its dominant terrain before its share
    falls under the floor."""

    def __init__(self, label: Labels, theta_min: float) -> None:
        area = collections.Counter(z for row in label for z in row if z >= 0)
        self.room: dict[int, int] = {z: math.floor((1 - theta_min) * n) for z, n in area.items()}

    def take(self, place: int) -> bool:
        if self.room[place] <= 0:
            return False
        self.room[place] -= 1
        return True

    def give(self, place: int) -> None:
        self.room[place] += 1


def theta_min(stats: PlaceStats) -> float:
    """The low decile of the corpus dominant share over every role, 1 without samples."""
    pooled = [v for values in stats.dominant_share.values() for v in values]
    return statistics.quantiles(pooled, n=THETA_QUANTILE)[0] if len(pooled) >= 2 else 1.0


def paint_priors(stats: PlaceStats, tables: MarkovTables) -> PaintPriors:
    """The paint priors of one level. A terrain with fewer than ``MIN_SAMPLES`` places or
    accents takes the rate or the sizes pooled over every terrain."""
    rates = [v for values in stats.accent_rate.values() for v in values]
    sizes = tuple(v for values in stats.accent_size.values() for v in values)
    pooled = statistics.fmean(rates) if rates else 0.0
    rate = {
        t: statistics.fmean(own)
        if len(own := stats.accent_rate.get(t.value, ())) >= MIN_SAMPLES
        else pooled
        for t in LAND
    }
    size = {
        t: own if len(own := stats.accent_size.get(t.value, ())) >= MIN_SAMPLES else sizes
        for t in LAND
    }
    return PaintPriors(theta_min(stats), stats.transition_width, rate, size, tables)


def band_widths(
    pairs: Sequence[Pair], widths: Sequence[int], rng: random.Random
) -> dict[Pair, int]:
    """Each border's band depth on either side, half a drawn corpus width, at most
    ``MAX_HALF_DEPTH``."""
    return {
        pq: min(MAX_HALF_DEPTH, half_depth(rng.choice(widths))) if widths else 0 for pq in pairs
    }


def crossing_chance(depth: int, width: int) -> float:
    """The chance a band tile ``depth`` steps from the border takes the far side's terrain,
    on a ramp that reaches one half at the border."""
    return (width - depth - 0.5) / (2 * width) if width else 0.0


def _neighbours(work: Work, x: int, y: int) -> list[Tile]:
    H, W = len(work), len(work[0])
    return [(x + dx, y + dy) for dx, dy in STEPS4 if 0 <= x + dx < W and 0 <= y + dy < H]


@dataclass(frozen=True, slots=True)
class Canvas:
    """The grid Paint writes, the place labels, each place's dominant terrain and the budget
    that keeps every place's dominant share at or above the floor."""

    work: Work
    label: Labels
    dominant: Mapping[int, Terrain]
    budget: Budget

    def swap(self, tile: Tile, t: int) -> bool:
        """Set ``tile`` to terrain ``t`` unless that would take its place under the floor.
        Returns whether the tile now holds ``t``."""
        x, y = tile
        here = self.work[y][x]
        if here == t:
            return True
        p = self.label[y][x]
        d = self.dominant[p].value
        if here == d and not self.budget.take(p):
            return False
        if t == d:
            self.budget.give(p)
        self.work[y][x] = t
        return True


def grade_bands(canvas: Canvas, widths: Mapping[Pair, int], rng: random.Random) -> frozenset[Tile]:
    """Grade every border in ``widths`` into the far side's terrain across its band, then
    smooth the band once. Returns the band, which holds at least the tiles on the border."""
    depth = border_depth(canvas.label, list(widths))
    band: set[Tile] = set()
    for (x, y), (d, q) in sorted(depth.items()):
        w = widths[pair(canvas.label[y][x], q)]
        if d >= max(1, w):
            continue
        band.add((x, y))
        if rng.random() < crossing_chance(d, w):
            _ = canvas.swap((x, y), canvas.dominant[q].value)
    smooth(canvas, {t: depth[t][1] for t in sorted(band)})
    return frozenset(band)


def smooth(canvas: Canvas, faced: Mapping[Tile, int]) -> None:
    """One sweep over the band tiles: a tile takes either side's terrain that at least
    ``SMOOTH_VOTES`` of its four neighbours carry."""
    work = canvas.work
    for (x, y), q in faced.items():
        sides = (canvas.dominant[canvas.label[y][x]].value, canvas.dominant[q].value)
        votes = collections.Counter(
            work[ny][nx] for nx, ny in _neighbours(work, x, y) if work[ny][nx] in sides
        )
        for t in sides:
            if t != work[y][x] and votes[t] >= SMOOTH_VOTES:
                _ = canvas.swap((x, y), t)


def inner_tiles(label: Labels, band: Collection[Tile]) -> dict[int, list[Tile]]:
    """Each place's tiles off its band and off every tile touching another place."""
    edge = boundary_tiles(label)
    out: dict[int, list[Tile]] = collections.defaultdict(list)
    for y, row in enumerate(label):
        for x, z in enumerate(row):
            if z >= 0 and (x, y) not in band and (x, y) not in edge:
                out[z].append((x, y))
    return dict(sorted(out.items()))


def poisson(lam: float, rng: random.Random) -> int:
    """A Poisson draw of mean ``lam`` by Knuth's product of uniforms."""
    floor, k, prod = math.exp(-lam), 0, rng.random()
    while prod > floor:
        k += 1
        prod *= rng.random()
    return k


def accent_weights(tables: MarkovTables, d: Terrain) -> collections.Counter[int]:
    """How often each other land terrain sits beside ``d`` inside a corpus place."""
    out: collections.Counter[int] = collections.Counter()
    for table in (tables.chain4.horiz, tables.chain4.vert):
        for (a, b), centre in table.items():
            for t, n in centre.items():
                if t != d and Terrain(t).is_land:
                    out[t] += n * ((a == d) + (b == d))
    return +out


def grow_accent(
    canvas: Canvas, spec: tuple[Tile, int, int], allowed: Collection[Tile], rng: random.Random
) -> int:
    """Grow one accent ``(start, size, terrain)`` by random breadth-first steps over
    ``allowed`` tiles still in the place's dominant terrain. Returns its size."""
    start, size, terrain = spec
    work = canvas.work
    d = canvas.dominant[canvas.label[start[1]][start[0]]].value
    frontier, grown = [start], 0
    while frontier and grown < size:
        i = rng.randrange(len(frontier))
        frontier[i], frontier[-1] = frontier[-1], frontier[i]
        x, y = frontier.pop()
        if work[y][x] != d or (x, y) not in allowed or not canvas.swap((x, y), terrain):
            continue
        grown += 1
        frontier.extend(_neighbours(work, x, y))
    return grown


def grow_accents(
    canvas: Canvas, inner: Mapping[int, Sequence[Tile]], priors: PaintPriors, seed: int
) -> None:
    """A Poisson number of accents per place at the corpus rate of its dominant terrain,
    each of a corpus size and of a terrain drawn from the corpus neighbours of the dominant,
    confined to the place's inner tiles."""
    work = canvas.work
    kinds = sorted(set(canvas.dominant.values()))
    weights = {d: accent_weights(priors.tables, d) for d in kinds}
    for p, tiles in inner.items():
        rng = stream(seed, "accents", p)
        d = canvas.dominant[p]
        n = poisson(priors.accent_rate[d] * len(tiles) / 100, rng)
        sizes = priors.accent_size[d]
        allowed = frozenset(tiles)
        for _ in range(n if weights[d] and sizes else 0):
            free = [(x, y) for x, y in tiles if work[y][x] == d]
            if not free:
                break
            terrain = sample(weights[d], rng)
            _ = grow_accent(canvas, (rng.choice(free), rng.choice(sizes), terrain), allowed, rng)


def _context(work: Work, x: int, y: int, tables: MarkovTables) -> collections.Counter[int]:
    lf, u, r, d = work[y][x - 1], work[y - 1][x], work[y][x + 1], work[y + 1][x]
    full = tables.chain4.full.get((lf, u, r, d))
    if full is not None and sum(full.values()) >= MIN_CONTEXT:
        return full
    dist = collections.Counter[int]()
    dist.update(tables.chain4.horiz.get((lf, r), {}))
    dist.update(tables.chain4.vert.get((u, d), {}))
    return dist


def texture_inside(
    canvas: Canvas, inner: Mapping[int, Sequence[Tile]], tables: MarkovTables, rng: random.Random
) -> None:
    """``SWEEPS`` Gibbs sweeps of the 4-neighbour conditional counted inside corpus places
    over every place's inner tiles. A tile with no counted context keeps its terrain."""
    work = canvas.work
    H, W = len(work), len(work[0])
    tiles = [(x, y) for ts in inner.values() for x, y in ts if 0 < x < W - 1 and 0 < y < H - 1]
    for _ in range(SWEEPS):
        rng.shuffle(tiles)
        for x, y in tiles:
            dist = _context(work, x, y, tables)
            if not dist:
                continue
            t = sample(dist, rng)
            if Terrain(t).is_land:
                _ = canvas.swap((x, y), t)


def restore_floor(
    grid: list[list[Terrain]], label: Labels, dominant: Mapping[int, Terrain], theta: float
) -> bool:
    """Give each place under ``theta`` its smallest off-dominant components back, in tile
    order, until its dominant share reaches ``theta`` again. Returns whether any tile
    changed."""
    off = off_dominant(grid, label, dominant)
    area = collections.Counter(z for row in label for z in row if z >= 0)
    owed = collections.Counter(off.values())
    for z in owed:
        owed[z] -= math.floor((1 - theta) * area[z])
    changed = False
    for comp in sorted(components(off, off), key=lambda c: (len(c), c[0])):
        z = off[comp[0]]
        if owed[z] > 0:
            for x, y in comp:
                grid[y][x] = dominant[z]
            owed[z] -= len(comp)
            changed = True
    return changed


def settle(canvas: Canvas, theta: float, thin: Collection[Terrain]) -> list[list[Terrain]]:
    """The tiler's erosion of tiles no 2x2 square holds, then the floor restored and the
    grid eroded again until erosion keeps every place at ``theta`` or the rounds run out."""
    grid = despeckle(canvas.work, thin, min_patch=0)
    for _ in range(MAX_RESTORE_ROUNDS):
        if not restore_floor(grid, canvas.label, canvas.dominant, theta):
            break
        grid = despeckle([[t.value for t in row] for row in grid], thin, min_patch=0)
    return grid


def paint_places(
    grid: Sequence[Sequence[Terrain]],
    places: LevelPlaces,
    priors: PaintPriors,
    seed: int,
    thin: Collection[Terrain],
) -> Painted:
    """Paint the base-coated ``grid`` of ``places``: bands, accents, texture, then
    ``settle``. Water and the labels stay as they are."""
    label = places.label
    dominant = {p: place.dominant for p, place in places.places.items()}
    canvas = Canvas(
        [[t.value for t in row] for row in grid], label, dominant, Budget(label, priors.theta_min)
    )
    soft = [pq for pq in sorted(label_adjacency(label)) if dominant[pq[0]] != dominant[pq[1]]]
    widths = band_widths(soft, priors.widths, stream(seed, "bands"))
    band = grade_bands(canvas, widths, stream(seed, "grade"))
    inner = inner_tiles(label, band)
    grow_accents(canvas, inner, priors, seed)
    texture_inside(canvas, inner, priors.tables, stream(seed, "texture"))
    return Painted(settle(canvas, priors.theta_min, thin), band)

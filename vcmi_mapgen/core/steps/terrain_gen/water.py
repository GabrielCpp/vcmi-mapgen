"""The topology surface form: all land while the places grow, then water carved on the
walls between touching territories no door joins, each band as wide as the wall between
them, and along the map edge, steered to one corpus map's water target. The land stays one
piece, every place stays one piece with half its tiles or more, and the home rooms and the
gate sites stay land."""

import math
import random
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import cast

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.grid.noise import value_noise
from vcmi_mapgen.core.jit import njit
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.priors.water import WaterTarget
from vcmi_mapgen.core.reading.water import edge_water_share
from vcmi_mapgen.core.steps.terrain_gen.coastline import Coastline, Shore, gate_tiles
from vcmi_mapgen.core.steps.terrain_gen.layout import Layout
from vcmi_mapgen.core.steps.terrain_gen.model import TerrainOptions
from vcmi_mapgen.core.steps.terrain_gen.streams import stream
from vcmi_mapgen.core.steps.terrain_gen.territories import wall_width

type Pair = tuple[int, int]
type Mask = NDArray[np.bool_]
type Labels = NDArray[np.int64]

MIN_WATER = 0.02
NO_WATER = WaterTarget(0.0, 0.0, 1)
EDGE_CELLS = 8
"""How many noise cells span the map side for the edge water's arcs."""


def draw_target(targets: Sequence[WaterTarget], rng: random.Random) -> WaterTarget:
    """One corpus map's water target, or no water without targets."""
    return rng.choice(targets) if targets else NO_WATER


@njit
def _one_piece(mask: Mask) -> bool:
    h, w = mask.shape
    queue: list[int] = []
    total = 0
    for y in range(h):
        for x in range(w):
            if mask[y, x]:
                total += 1
                if not queue:
                    queue.append(y * w + x)
    if total == 0:
        return True
    seen = np.zeros((h, w), np.bool_)
    seen[queue[0] // w, queue[0] % w] = True
    head = 0
    while head < len(queue):
        y, x = divmod(queue[head], w)
        head += 1
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                queue.append(ny * w + nx)
    return len(queue) == total


def _is(label: Labels, value: int) -> Mask:
    return cast("Mask", np.equal(label, value))


def _grow(mask: Mask) -> Mask:
    out = mask.copy()
    out[1:, :] |= mask[:-1, :]
    out[:-1, :] |= mask[1:, :]
    out[:, 1:] |= mask[:, :-1]
    out[:, :-1] |= mask[:, 1:]
    return out


def _pieces(mask: Mask) -> list[Mask]:
    seen = np.zeros(mask.shape, np.bool_)
    out: list[Mask] = []
    ys, xs = np.nonzero(mask)
    for y, x in zip(cast("list[int]", ys.tolist()), cast("list[int]", xs.tolist()), strict=True):
        if seen[y, x]:
            continue
        piece = np.zeros(mask.shape, np.bool_)
        piece[y, x] = True
        while (more := _grow(piece) & mask & ~piece).any():
            piece |= more
        seen |= piece
        out.append(piece)
    return out


@dataclass(slots=True)
class Front:
    """One stretch of land the water may take: the tiles it may take, the line it starts
    from, the layers its first carve takes, the tiles it has taken, and whether it still
    grows."""

    region: Mask
    line: Mask
    first: int
    wet: Mask
    open: bool = True


@dataclass(slots=True)
class Flood:
    """The label grid as the carve goes, each place's tile count before it, and the tiles
    that stay land."""

    label: Labels
    area: NDArray[np.int64]
    keep: Mask

    def take(self, tiles: Mask) -> Mask:
        """The tiles of ``tiles`` the flood takes: each 4-connected piece in turn that
        leaves the land one piece and every place it touches one piece with half its old
        tiles or more."""
        tiles = tiles & ~self.keep & (self.label >= 0)
        taken = np.zeros(tiles.shape, np.bool_)
        for piece in _pieces(tiles):
            touched = cast("list[int]", np.unique(self.label[piece]).tolist())
            trial = self.label.copy()
            trial[piece] = -1
            if not _one_piece(trial >= 0):
                continue
            if any(
                np.count_nonzero(_is(trial, p)) * 2 < self.area.item(p)
                or not _one_piece(_is(trial, p))
                for p in touched
            ):
                continue
            self.label = trial
            taken |= piece
        return taken

    def share(self) -> float:
        """The share of the map under water so far."""
        return float(np.mean(self.label < 0))

    def carve(self, front: Front) -> int:
        """Take ``front``'s first layers from its line outward, each layer from the tiles
        taken so far, and stop when a layer takes nothing. Returns 1 when the front took a
        tile, else 0."""
        layer = front.line & front.region
        for _ in range(front.first):
            taken = self.take(layer)
            front.wet |= taken
            if not taken.any():
                front.open = False
                break
            layer = _grow(front.wet) & front.region & ~front.wet
        return int(front.wet.any())

    def deepen(self, front: Front) -> None:
        """Take one more layer of ``front`` around the tiles it has taken."""
        taken = self.take(_grow(front.wet) & front.region & ~front.wet)
        front.wet |= taken
        front.open = bool(taken.any())


def walled_fronts(
    label: Labels, territory: Sequence[int], doors: Sequence[Pair], depths: Mapping[Pair, int]
) -> dict[Pair, int]:
    """Every pair of touching territories no door joins, with the widest wall between two of
    their zones, one tile when ``depths`` has none."""
    joined = {(min(territory[a], territory[b]), max(territory[a], territory[b])) for a, b in doors}
    out: dict[Pair, int] = {}
    for a, b in ((label[:, :-1], label[:, 1:]), (label[:-1, :], label[1:, :])):
        both = (a >= 0) & (b >= 0) & np.not_equal(a, b)
        za_all = cast("list[int]", a[both].tolist())
        zb_all = cast("list[int]", b[both].tolist())
        for za, zb in set(zip(za_all, zb_all, strict=True)):
            ta, tb = territory[za], territory[zb]
            key = (min(ta, tb), max(ta, tb))
            if ta == tb or key in joined:
                continue
            width = depths.get((min(za, zb), max(za, zb)), 1)
            out[key] = max(out.get(key, 1), width)
    return out


def front_of(label: Labels, owner: Labels, pair: Pair, width: int) -> Front:
    """The front between the two territories of ``pair``: their tiles, the line where they
    touch, and half ``width`` rounded up as its first layers."""
    a = _is(owner, pair[0])
    b = _is(owner, pair[1])
    line = (a & _grow(b)) | (b & _grow(a))
    region = (a | b) & (label >= 0)
    return Front(region, line, math.ceil(width / 2), np.zeros(label.shape, np.bool_))


def edge_front(side: int, edge: float, rng: random.Random) -> Front:
    """The edge water's front: the high ground of a smooth noise field, its tiles on the
    map's outer ring as the line, about ``edge`` of the ring, and half a cut-off wall as its
    first layers."""
    noise = np.array(value_noise(side, side, max(2, side // EDGE_CELLS), rng))
    ring: Mask = np.ones((side, side), np.bool_)
    ring[1:-1, 1:-1] = False
    cut = float(np.quantile(noise[ring], 1 - edge)) if edge > 0 else math.inf
    region = noise > cut
    first = max(1, wall_width(None, side) // 2)
    return Front(region, region & ring, first, np.zeros(region.shape, np.bool_))


def _keep_mask(keep: Collection[Tile], side: int) -> Mask:
    mask: Mask = np.zeros((side, side), np.bool_)
    for x, y in keep:
        if 0 <= x < side and 0 <= y < side:
            mask[y, x] = True
    return mask


def _open(flood: Flood, fronts: tuple[list[Front], list[Front]], n: int, share: float) -> int:
    """Carve the next ``n`` waiting fronts while the flood stays under ``share``, moving
    each to the growing ones. Returns how many of them took a tile."""
    waiting, growing = fronts
    count = 0
    for _ in range(min(n, len(waiting))):
        if flood.share() >= share:
            break
        front = waiting.pop(0)
        count += flood.carve(front)
        growing.append(front)
    return count


def water_on_walls(
    shore: Shore, target: WaterTarget, side: int, rng: random.Random
) -> tuple[Layout, int]:
    """``shore``'s layout with water carved toward ``target``, and how many walled fronts
    took water. The fronts between touching territories no door joins go widest first, the
    ties in random order, ``target.masses`` of them or one, each a band half its wall width
    deep on either side of the line where the two territories touch. The edge water then
    takes the noise arcs of the ring. While the share stays under the target the carved
    fronts and the edge deepen one layer each in turn, and the next walled front joins when
    none of them can."""
    label = np.array(shore.layout.label, dtype=np.int64)
    owner = np.where(label >= 0, np.array(shore.territory, dtype=np.int64)[label], -1)
    area = np.bincount(label[label >= 0], minlength=shore.layout.places).astype(np.int64)
    flood = Flood(label, area, _keep_mask(shore.keep, side))
    walls = walled_fronts(label, shore.territory, sorted(shore.doors), shore.depths)
    ranked = sorted(walls, key=lambda p: (-walls[p], rng.random(), p))
    fronts: tuple[list[Front], list[Front]] = (
        [front_of(label, owner, pair, walls[pair]) for pair in ranked],
        [],
    )
    count = _open(flood, fronts, max(1, target.masses), target.share)
    edge = edge_front(side, target.edge, rng)
    if flood.share() < target.share:
        _ = flood.carve(edge)
    fronts[1].append(edge)
    while flood.share() < target.share:
        live = [f for f in fronts[1] if f.open and f.wet.any()]
        if not live and not fronts[0]:
            break
        if not live:
            count += _open(flood, fronts, 1, target.share)
        for front in live:
            if flood.share() >= target.share:
                break
            flood.deepen(front)
    return replace(shore.layout, label=cast("list[list[int]]", flood.label.tolist())), count


class TopologyForm:
    """All land while the places grow, then water on the walls no door crosses."""

    def land(self, priors: Priors, seed: int, options: TerrainOptions) -> Coastline:
        target = draw_target(priors.water.targets, stream(seed, "water"))
        size = options.size
        land = [[True] * size for _ in range(size)]
        return Coastline(land, round(size * size * (1 - target.share)))

    def flood(
        self, shore: Shore, priors: Priors, seed: int, options: TerrainOptions, /
    ) -> tuple[Layout, tuple[str, ...]]:
        target = draw_target(priors.water.targets, stream(seed, "water"))
        size = options.size
        if target.share < MIN_WATER:
            return shore.layout, (_line(target, np.zeros((size, size), np.bool_), 0),)
        shore = replace(shore, keep=shore.keep | gate_tiles(seed, options))
        layout, fronts = water_on_walls(shore, target, size, stream(seed, "water_walls"))
        water = np.array(layout.label) < 0
        return layout, (_line(target, water, fronts),)


def _line(target: WaterTarget, water: Mask, fronts: int) -> str:
    return (
        f"  water: target share {target.share:.2f}, edge {target.edge:.2f}, "
        + f"{target.masses} masses; drawn share {float(np.mean(water)):.2f}, "
        + f"edge {edge_water_share(water):.2f}, {fronts} fronts carved"
    )

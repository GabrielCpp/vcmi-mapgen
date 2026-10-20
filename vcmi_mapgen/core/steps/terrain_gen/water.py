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
type Field = NDArray[np.float64]

MIN_WATER = 0.02
SHORE_MARGIN = 2.0
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


def _layers(region: Mask, line: Mask) -> Field:
    """Each tile of ``region``'s 4-connected steps from ``line`` inside ``region``, 0 on the
    line, infinite off the region and where the line does not reach."""
    out: Field = np.full(region.shape, math.inf)
    seen = line & region
    out[seen] = 0.0
    step = 0
    while (more := _grow(seen) & region & ~seen).any():
        step += 1
        out[more] = float(step)
        seen |= more
    return out


def _rank(region: Mask, line: Mask, coast: Field) -> Field:
    layer = _layers(region, line)
    on_line = cast("Mask", np.equal(layer, 0.0))
    inland = _layers(np.ones(region.shape, np.bool_), ~region)
    held = inland <= SHORE_MARGIN + 0.5 * coast
    return cast("Field", np.where(on_line, 0.0, np.where(held, math.inf, layer + coast)))


@dataclass(slots=True)
class Front:
    """One stretch of land the water may take: the tiles it may take, the line it starts
    from, the layers its first carve takes, the tiles it has taken, and whether it still
    grows. With a coast noise it also holds ``rank``, each region tile's layer from the
    line plus the coast field there and 0 on the line, infinite off the region and within
    ``SHORE_MARGIN`` plus half the coast field of its edge, the
    ``level`` of rank the water has reached and ``top``, the largest finite rank. The water
    then takes a tile once its rank is within the level, so the coast wanders around the
    uniform offset of the layers. Without it ``rank`` is None."""

    region: Mask
    line: Mask
    first: int
    wet: Mask
    open: bool = True
    rank: Field | None = None
    level: float = 0.0
    top: float = 0.0


@dataclass(slots=True)
class Flood:
    """The label grid as the carve goes, each place's tile count before it, the tiles
    that stay land, and whether a refused piece is split and tried again."""

    label: Labels
    area: NDArray[np.int64]
    keep: Mask
    split: bool = False

    def take(self, tiles: Mask) -> Mask:
        """The tiles of ``tiles`` the flood takes: each 4-connected piece in turn that
        leaves the land one piece and every place it touches one piece with half its old
        tiles or more. A splitting flood also takes the smaller parts of a place the piece
        cuts in two, and cuts a refused piece in two across its longer side and tries each
        half's pieces again, down to single tiles."""
        tiles = tiles & ~self.keep & (self.label >= 0)
        taken = np.zeros(tiles.shape, np.bool_)
        for piece in _pieces(tiles):
            if self.split:
                taken |= self._take_split(piece)
            elif (got := self._try(piece)) is not None:
                taken |= got
        return taken

    def _try(self, piece: Mask) -> Mask | None:
        piece = piece & (self.label >= 0)
        if not piece.any():
            return None
        touched = cast("list[int]", np.unique(self.label[piece]).tolist())
        trial = self.label.copy()
        trial[piece] = -1
        if self.split:
            for p in touched:
                parts = sorted(_pieces(_is(trial, p)), key=np.count_nonzero)
                for part in parts[:-1]:
                    if (part & self.keep).any():
                        return None
                    trial[part] = -1
        if not _one_piece(trial >= 0):
            return None
        if any(
            np.count_nonzero(_is(trial, p)) * 2 < self.area.item(p) or not _one_piece(_is(trial, p))
            for p in touched
        ):
            return None
        got = (trial < 0) & (self.label >= 0)
        self.label = trial
        return got

    def _take_split(self, piece: Mask) -> Mask:
        if (got := self._try(piece)) is not None:
            return got
        taken = np.zeros(piece.shape, np.bool_)
        across = cast("Mask", np.any(piece, axis=1))
        down = cast("Mask", np.any(piece, axis=0))
        rows = cast("list[int]", np.flatnonzero(across).tolist())
        cols = cast("list[int]", np.flatnonzero(down).tolist())
        if len(rows) == 1 and len(cols) == 1:
            return taken
        half = piece.copy()
        if cols[-1] - cols[0] >= rows[-1] - rows[0]:
            half[:, (cols[0] + cols[-1]) // 2 + 1 :] = False
        else:
            half[(rows[0] + rows[-1]) // 2 + 1 :, :] = False
        for part in (half, piece & ~half):
            for sub in _pieces(part & (self.label >= 0)):
                taken |= self._take_split(sub)
        return taken

    def share(self) -> float:
        """The share of the map under water so far."""
        return float(np.mean(self.label < 0))

    def carve(self, front: Front) -> int:
        """Take ``front``'s first layers from its line outward, each layer from the tiles
        taken so far, and stop when a layer takes nothing. Returns 1 when the front took a
        tile, else 0. A front with a coast rank takes its line, then each level up to the first
        layers by rank, and closes only when its line takes nothing."""
        if front.rank is not None:
            taken = self.take(front.line & front.region)
            front.wet |= taken
            if not taken.any():
                front.open = False
                return 0
            for k in range(1, front.first):
                front.level = float(k)
                _ = self._take_level(front)
            return int(front.wet.any())
        layer = front.line & front.region
        for _ in range(front.first):
            taken = self.take(layer)
            front.wet |= taken
            if not taken.any():
                front.open = False
                break
            layer = _grow(front.wet) & front.region & ~front.wet
        return int(front.wet.any())

    def _take_level(self, front: Front) -> Mask:
        assert front.rank is not None
        total = np.zeros(front.wet.shape, np.bool_)
        while True:
            cand = _grow(self.label < 0) & front.region & ~front.wet & (front.rank <= front.level)
            taken = self.take(cand)
            if not taken.any():
                return total
            front.wet |= taken
            total |= taken

    def deepen(self, front: Front) -> None:
        """Take one more layer of ``front`` around the tiles it has taken. A front with a
        coast rank raises its level until a level takes a tile, and closes once the level
        passes its top rank."""
        if front.rank is not None:
            while True:
                front.level += 1
                if self._take_level(front).any():
                    front.open = True
                    return
                if front.level > front.top:
                    front.open = False
                    return
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


def _front(region: Mask, line: Mask, first: int, coast: Field | None) -> Front:
    wet: Mask = np.zeros(region.shape, np.bool_)
    if coast is None:
        return Front(region, line, first, wet)
    rank = _rank(region, line, coast)
    finite = rank[np.isfinite(rank)]
    top = float(np.max(finite)) if finite.size else 0.0
    return Front(region, line, first, wet, rank=rank, top=top)


def front_of(
    label: Labels, owner: Labels, pair: Pair, width: int, coast: Field | None = None
) -> Front:
    """The front between the two territories of ``pair``: their tiles, the line where they
    touch, and half ``width`` rounded up as its first layers. A ``coast`` field gives it a
    ranked coast."""
    a = _is(owner, pair[0])
    b = _is(owner, pair[1])
    line = (a & _grow(b)) | (b & _grow(a))
    region = (a | b) & (label >= 0)
    return _front(region, line, math.ceil(width / 2), coast)


def edge_front(side: int, edge: float, rng: random.Random, coast: Field | None = None) -> Front:
    """The edge water's front: the high ground of a smooth noise field, its tiles on the
    map's outer ring as the line, about ``edge`` of the ring, and half a cut-off wall as its
    first layers. A ``coast`` field gives it a ranked coast."""
    noise = np.array(value_noise(side, side, max(2, side // EDGE_CELLS), rng))
    ring: Mask = np.ones((side, side), np.bool_)
    ring[1:-1, 1:-1] = False
    cut = float(np.quantile(noise[ring], 1 - edge)) if edge > 0 else math.inf
    region = noise > cut
    first = max(1, wall_width(None, side) // 2)
    return _front(region, region & ring, first, coast)


def _keep_mask(keep: Collection[Tile], side: int) -> Mask:
    mask: Mask = np.zeros((side, side), np.bool_)
    for x, y in keep:
        if 0 <= x < side and 0 <= y < side:
            mask[y, x] = True
    return mask


def _keep_margin(keep: Mask, coast: Field) -> Mask:
    """The disc around each 4-connected piece of kept tiles: its centre, the reach of its
    farthest tile plus ``SHORE_MARGIN``, swayed by half the coast field, so the coast rounds a
    kept room instead of tracing its sides."""
    axis: Field = np.arange(keep.shape[0], dtype=np.float64)
    out: Mask = np.zeros(keep.shape, np.bool_)
    for piece in _pieces(keep):
        ys, xs = cast("tuple[Labels, Labels]", np.nonzero(piece))
        cy, cx = float(np.mean(ys)), float(np.mean(xs))
        reach = float(np.max(cast("Field", np.hypot(xs - cx, ys - cy))))
        near: Field = np.hypot(axis[None, :] - cx, axis[:, None] - cy)
        out |= near <= reach + SHORE_MARGIN + 0.5 * coast
    return out


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
    shore: Shore, target: WaterTarget, side: int, rng: random.Random, coast: Field | None = None
) -> tuple[Layout, int]:
    """``shore``'s layout with water carved toward ``target``, and how many walled fronts
    took water. The fronts between touching territories no door joins go widest first, the
    ties in random order, ``target.masses`` of them or one, each a band half its wall width
    deep on either side of the line where the two territories touch. The edge water then
    takes the noise arcs of the ring. While the share stays under the target the carved
    fronts and the edge deepen one layer each in turn, and the next walled front joins when
    none of them can, until ``target.masses`` of them or one have taken water. A ``coast``
    field, in tiles over the map, sways every front's layers: a tile joins the water once its
    layer from the line plus the field there is within the front's level, so the coast
    wanders around the border instead of following it at a fixed offset. Without it the
    layers are uniform. The coast draws nothing from ``rng``."""
    label = np.array(shore.layout.label, dtype=np.int64)
    owner = np.where(label >= 0, np.array(shore.territory, dtype=np.int64)[label], -1)
    area = np.bincount(label[label >= 0], minlength=shore.layout.places).astype(np.int64)
    keep = _keep_mask(shore.keep, side)
    if coast is not None:
        keep |= _keep_margin(keep, coast)
    flood = Flood(label, area, keep, split=coast is not None)
    walls = walled_fronts(label, shore.territory, sorted(shore.doors), shore.depths)
    ranked = sorted(walls, key=lambda p: (-walls[p], rng.random(), p))
    fronts: tuple[list[Front], list[Front]] = (
        [front_of(label, owner, pair, walls[pair], coast) for pair in ranked],
        [],
    )
    cap = max(1, target.masses)
    count = _open(flood, fronts, cap, target.share)
    edge = edge_front(side, target.edge, rng, coast)
    if flood.share() < target.share:
        _ = flood.carve(edge)
    fronts[1].append(edge)
    while flood.share() < target.share:
        live = [f for f in fronts[1] if f.open and f.wet.any()]
        if not live and (not fronts[0] or count >= cap):
            break
        if not live:
            count += _open(flood, fronts, 1, target.share)
        for front in live:
            if flood.share() >= target.share:
                break
            flood.deepen(front)
    return replace(shore.layout, label=cast("list[list[int]]", flood.label.tolist())), count


class TopologyForm:
    """All land while the places grow, then water on the walls no door crosses. A positive
    ``coast``, in tiles, sways the coast with two octaves of value noise at that amplitude."""

    def __init__(self, coast: float = 0.0) -> None:
        self.coast: float = coast

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
        field = None
        if self.coast > 0:
            n0 = np.asarray(
                value_noise(size, size, max(2, size // 9), stream(seed, "coast", 0)),
                dtype=np.float64,
            )
            n1 = np.asarray(
                value_noise(size, size, max(2, size // 24), stream(seed, "coast", 1)),
                dtype=np.float64,
            )
            field = self.coast * (n0 + 0.5 * n1)
        layout, fronts = water_on_walls(shore, target, size, stream(seed, "water_walls"), field)
        water = np.array(layout.label) < 0
        return layout, (_line(target, water, fronts, self.coast),)


def _line(target: WaterTarget, water: Mask, fronts: int, coast: float = 0.0) -> str:
    swayed = f", coast noise {coast:g}" if coast > 0 else ""
    return (
        f"  water: target share {target.share:.2f}, edge {target.edge:.2f}, "
        + f"{target.masses} masses; drawn share {float(np.mean(water)):.2f}, "
        + f"edge {edge_water_share(water):.2f}, {fronts} fronts carved{swayed}"
    )

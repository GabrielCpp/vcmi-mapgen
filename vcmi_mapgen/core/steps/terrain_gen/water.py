"""The topology surface form: all land while the places grow, then water carved on the
walls between touching territories no door joins, each band as wide as the wall between
them, and along the map edge, steered to one corpus map's water target. The land stays one
piece through land ``LINK`` tiles wide, or in coast mode as many big masses as the target
holds, every place stays one piece
with half its tiles or more, and the home rooms and the gate sites stay land."""

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
from vcmi_mapgen.core.reading.water import MASS_SHARE, edge_water_share
from vcmi_mapgen.core.steps.terrain_gen.coastline import Coastline, Shore, gate_tiles
from vcmi_mapgen.core.steps.terrain_gen.islands import raise_islands
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
SMOOTH = 2.5
"""The blur, in tiles, that rounds the edge water's coast."""
TAPER = 4.0
"""How many levels the edge water's arc takes to reach its ends from its crest."""
WIDTHS = (2.5, 4.0)
"""The widths, in tiles, a coast-mode channel network is drawn for: corpus channels run two
to four tiles wide."""
EDGE_REACH = 6.0
"""How far, in tiles, the edge sea reaches inland on average, so the inland channels take
the rest of the water share."""
LINK = 3
"""The narrowest land, in tiles, that joins two parts of the land: a thinner strip between
two waters reads as a tunnel, which hand-made maps leave out."""


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


@njit
def _piece_size(mask: Mask, seen: Mask, y0: int, x0: int) -> int:
    h, w = mask.shape
    seen[y0, x0] = True
    queue = [y0 * w + x0]
    head = 0
    while head < len(queue):
        y, x = divmod(queue[head], w)
        head += 1
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                queue.append(ny * w + nx)
    return len(queue)


@njit
def _big_pieces(mask: Mask, share: float) -> int:
    h, w = mask.shape
    seen = np.zeros((h, w), np.bool_)
    cut = share * max(np.count_nonzero(mask), 1)
    big = 0
    for y0 in range(h):
        for x0 in range(w):
            if mask[y0, x0] and not seen[y0, x0] and _piece_size(mask, seen, y0, x0) >= cut:
                big += 1
    return big


def _wide(mask: Mask) -> Mask:
    """The tiles of ``mask`` inside a ``LINK`` by ``LINK`` square of ``mask``."""
    out = np.zeros(mask.shape, np.bool_)
    h, w = mask.shape
    if h < LINK or w < LINK:
        return out
    square = np.ones((h - LINK + 1, w - LINK + 1), np.bool_)
    for dy in range(LINK):
        for dx in range(LINK):
            square &= mask[dy : dy + h - LINK + 1, dx : dx + w - LINK + 1]
    for dy in range(LINK):
        for dx in range(LINK):
            out[dy : dy + h - LINK + 1, dx : dx + w - LINK + 1] |= square
    return out


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


DIAG = math.sqrt(2.0)
BEHIND = ((0, -1, 1.0), (-1, 0, 1.0), (-1, -1, DIAG), (-1, 1, DIAG))
AHEAD = ((0, 1, 1.0), (1, 0, 1.0), (1, 1, DIAG), (1, -1, DIAG))


@njit
def _chamfer_pass(out: Field, steps: tuple[tuple[int, int, float], ...], back: bool) -> None:
    h, w = out.shape
    n = h * w
    for i in range(n):
        k = n - 1 - i if back else i
        y = k // w
        x = k - y * w
        for dy, dx, cost in steps:
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and out[ny, nx] + cost < out[y, x]:
                out[y, x] = out[ny, nx] + cost


def _chamfer(seed: Mask) -> Field:
    out: Field = np.where(seed, 0.0, float(seed.shape[0] + seed.shape[1]))
    _chamfer_pass(out, BEHIND, False)
    _chamfer_pass(out, AHEAD, True)
    return out


def _blur(field: Field, sigma: float) -> Field:
    radius = max(1, math.ceil(3 * sigma))
    taps = [math.exp(-0.5 * (d / sigma) ** 2) for d in range(-radius, radius + 1)]
    total = sum(taps)
    out: Field = field
    for axis in (0, 1):
        pad = [(0, 0), (0, 0)]
        pad[axis] = (radius, radius)
        padded: Field = np.pad(out, pad, mode="edge")
        n = out.shape[axis]
        acc: Field = np.zeros(out.shape, np.float64)
        for k, tap in enumerate(taps):
            acc += (tap / total) * np.take(padded, np.arange(k, k + n), axis=axis)
        out = acc
    return out


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
    limit: float = math.inf


@dataclass(slots=True)
class Flood:
    """The label grid as the carve goes, each place's tile count before it, the tiles
    that stay land, and whether the flood is loose: a refused piece is then split and tried
    again, a place may fall in pieces, which `rejoin` hands to their neighbours, and the land
    may part in up to ``masses`` big masses, each with ``MASS_SHARE`` of the land or more."""

    label: Labels
    area: NDArray[np.int64]
    keep: Mask
    loose: bool = False
    masses: int = 1

    def take(self, tiles: Mask) -> Mask:
        """The tiles of ``tiles`` the flood takes: each 4-connected piece in turn that
        leaves the land one piece through its ``LINK``-wide squares, or a loose flood's land
        in no more big masses than ``masses``, and every place it touches one piece with half
        its old tiles or more. A loose flood lets the place fall in pieces while its largest piece
        keeps half its old tiles, and cuts a refused piece in two across its longer side and
        tries each half's pieces again, down to single tiles."""
        tiles = tiles & ~self.keep & (self.label >= 0)
        taken = np.zeros(tiles.shape, np.bool_)
        for piece in _pieces(tiles):
            if self.loose:
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
        if not self._whole(trial >= 0):
            return None
        if any(self._kept(trial, p) * 2 < self.area.item(p) for p in touched):
            return None
        got = (trial < 0) & (self.label >= 0)
        self.label = trial
        return got

    def _whole(self, land: Mask) -> bool:
        wide = _wide(land)
        if not self.loose or self.masses <= 1:
            return _one_piece(wide)
        return max(_big_pieces(wide, MASS_SHARE), _big_pieces(land, MASS_SHARE)) <= self.masses

    def _kept(self, trial: Labels, p: int) -> int:
        mine = _is(trial, p)
        if not self.loose:
            return np.count_nonzero(mine) if _one_piece(mine) else 0
        return max((np.count_nonzero(m) for m in _pieces(mine)), default=0)

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

    def rejoin(self) -> None:
        """Hand every piece of a place but its largest to the place it borders on the most
        tiles, so each place is one piece again."""
        for p in range(self.area.size):
            pieces = sorted(_pieces(_is(self.label, p)), key=lambda m: -np.count_nonzero(m))
            for piece in pieces[1:]:
                rim = cast("Mask", _grow(piece) & ~piece & (self.label >= 0) & (self.label != p))
                if not rim.any():
                    continue
                votes = np.bincount(self.label[rim], minlength=self.area.size)
                self.label[piece] = int(np.argmax(votes))

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
                if front.level + 1 > front.limit:
                    front.open = False
                    return
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


def _front(region: Mask, line: Mask, first: int, rank: Field | None) -> Front:
    wet: Mask = np.zeros(region.shape, np.bool_)
    if rank is None:
        return Front(region, line, first, wet)
    finite = rank[np.isfinite(rank)]
    if not finite.size:
        return Front(region, line & False, first, wet, rank=rank)
    low = float(np.min(finite))
    line = region & (rank <= max(low, 0.5))
    return Front(region, line, first, wet, rank=rank - low, top=float(np.max(finite)) - low)


def front_of(label: Labels, owner: Labels, pair: Pair, width: int) -> Front:
    """The front between the two territories of ``pair``: their tiles, the line where they
    touch, and half ``width`` rounded up as its first layers."""
    a = _is(owner, pair[0])
    b = _is(owner, pair[1])
    line = (a & _grow(b)) | (b & _grow(a))
    region = (a | b) & (label >= 0)
    return _front(region, line, math.ceil(width / 2), None)


def _contour(noise: Field, land: Mask) -> Mask:
    high = noise > float(np.median(noise[land]))
    out = np.zeros(high.shape, np.bool_)
    out[:, :-1] |= high[:, :-1] != high[:, 1:]
    out[:-1, :] |= high[:-1, :] != high[1:, :]
    return out & land


def contour_front(land: Mask, share: float, coast: Field, rng: random.Random) -> Front:
    """One front over the median isolines of a smooth noise field, its wavelength chosen so
    the target share spread along the lines makes a channel about as wide as a width drawn
    between ``WIDTHS``. Each land tile ranks by its distance to the nearest line, swayed by
    half the coast field and blurred, so the channels keep an even width and round corners."""
    side = land.shape[0]
    width = rng.uniform(*WIDTHS)
    best: tuple[float, Mask] | None = None
    for cell in range(4, side + 1, 2):
        noise = _blur(np.asarray(value_noise(side, side, cell, rng), dtype=np.float64), 1.0)
        line = _contour(noise, land)
        tiles = np.count_nonzero(line)
        if tiles == 0:
            continue
        miss = abs(math.log(share * side * side / tiles / width))
        if best is None or miss < best[0]:
            best = (miss, line)
    if best is None:
        empty = np.zeros(land.shape, np.bool_)
        return Front(land, empty, 1, empty, rank=None)
    sway = 0.5 * (coast - float(np.mean(coast)))
    rank = _blur(_chamfer(best[1]) + sway, 1.0)
    rank = rank - float(np.min(rank[best[1]]))
    return _front(land, land, 1, cast("Field", np.where(land, rank, math.inf)))


def edge_front(side: int, edge: float, rng: random.Random, coast: Field | None = None) -> Front:
    """The edge water's front: the high ground of a smooth noise field, its tiles on the
    map's outer ring as the line, about ``edge`` of the ring, and half a cut-off wall as its
    first layers. A ``coast`` field gives it a ranked coast."""
    noise = np.array(value_noise(side, side, max(2, side // EDGE_CELLS), rng))
    ring: Mask = np.ones((side, side), np.bool_)
    ring[1:-1, 1:-1] = False
    cut = float(np.quantile(noise[ring], 1 - edge)) if edge > 0 else math.inf
    region = noise > cut
    first = max(1, wall_width(None) // 2)
    if coast is None:
        return _front(region, region & ring, first, None)
    touching: Mask = np.zeros((side, side), np.bool_)
    for piece in _pieces(region):
        if (piece & ring).any():
            touching |= piece
    region = touching
    crest = float(cast("float", np.max(noise)))
    height = np.clip((noise - cut) / max(crest - cut, 1e-9), 0.0, 1.0)
    axis = np.arange(side)
    depth = np.minimum.outer(np.minimum(axis, side - 1 - axis), np.minimum(axis, side - 1 - axis))
    sway = _blur(coast, SMOOTH)
    rank = depth + TAPER * (1.0 - height) + sway - float(np.min(sway))
    return _front(region, region, first, cast("Field", np.where(region, rank, math.inf)))


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
    flood = Flood(label, area, keep, loose=coast is not None, masses=target.masses)
    walls = walled_fronts(label, shore.territory, sorted(shore.doors), shore.depths)
    if coast is not None:
        return _water_by_network(shore, target, rng, coast, flood)
    ranked = sorted(walls, key=lambda p: (-walls[p], rng.random(), p))
    fronts: tuple[list[Front], list[Front]] = (
        [front_of(label, owner, pair, walls[pair]) for pair in ranked],
        [],
    )
    cap = max(1, target.masses)
    count = _open(flood, fronts, cap, target.share)
    edge = edge_front(side, target.edge, rng)
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


def _water_by_network(
    shore: Shore, target: WaterTarget, rng: random.Random, coast: Field, flood: Flood
) -> tuple[Layout, int]:
    """The coast-mode flood: the edge sea and a channel network over the contour lines of a
    noise field, deepened in turn to the target share, then the places made one piece each.
    Returns the layout and how many walled territory pairs a channel touches on both sides."""
    side = flood.label.shape[0]
    owner = np.where(flood.label >= 0, np.array(shore.territory, dtype=np.int64)[flood.label], -1)
    walls = walled_fronts(flood.label, shore.territory, sorted(shore.doors), shore.depths)
    edge = edge_front(side, target.edge, rng, coast)
    inland = max(target.share - target.edge * 4 / side * EDGE_REACH, 0.5 * target.share)
    network = contour_front(flood.label >= 0, inland, coast, rng)
    growing = [f for f in (network, edge) if f.rank is not None]
    for front in growing:
        if flood.share() < target.share:
            _ = flood.carve(front)
    while flood.share() < target.share:
        live = [f for f in growing if f.open and f.wet.any()]
        if not live:
            if network.rank is None or not network.wet.any() or network.limit >= network.top:
                break
            network.limit += 1.0
            network.open = True
            continue
        for front in live:
            if flood.share() >= target.share:
                break
            flood.deepen(front)
    flood.rejoin()
    owner_wet: Labels = owner[network.wet]
    carved = sum(1 for a, b in walls if a in owner_wet and b in owner_wet)
    return replace(shore.layout, label=cast("list[list[int]]", flood.label.tolist())), carved


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
        isles = replace(target, share=target.share + sum(target.islands))
        layout, fronts = water_on_walls(shore, isles, size, stream(seed, "water_walls"), field)
        label, places = raise_islands(
            np.array(layout.label, dtype=np.int64),
            target.islands,
            layout.places,
            stream(seed, "islands"),
        )
        layout = replace(layout, label=cast("list[list[int]]", label.tolist()), places=places)
        water = label < 0
        return layout, (_line(target, water, fronts, self.coast),)


def _line(target: WaterTarget, water: Mask, fronts: int, coast: float = 0.0) -> str:
    swayed = f", coast noise {coast:g}" if coast > 0 else ""
    return (
        f"  water: target share {target.share:.2f}, edge {target.edge:.2f}, "
        + f"{target.masses} masses; drawn share {float(np.mean(water)):.2f}, "
        + f"edge {edge_water_share(water):.2f}, {fronts} fronts carved{swayed}, "
        + f"{len(target.islands)} islands drawn"
    )

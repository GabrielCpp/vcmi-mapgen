"""The zone canvas every vegetation sampler grows on: the zone's local grids, the protected
web, the blocking count, and the legality and connectivity rules every placement and every
removal obeys."""

import random
from collections.abc import Collection, Mapping, Sequence
from collections.abc import Set as AbstractSet
from typing import cast

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.grid.geometry import EBINS, edge_dist
from vcmi_mapgen.core.model import PlacedObject, Tile
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.planning.web import ZoneRef, protected_web
from vcmi_mapgen.core.steps.vegetation.connect import frees_connected, keeps_connected
from vcmi_mapgen.core.steps.vegetation.model import VegModel
from vcmi_mapgen.core.steps.vegetation.sampler import SampleOptions, ZoneGrowth


def zone_rng(zone: ZoneRef, seed: int) -> random.Random:
    """The zone's own random stream, mixed from the run seed and the zone id."""
    return random.Random(seed ^ (zone.zid * 2654435761 & 0xFFFFFFFF))


class ZoneCanvas:
    """One zone's grids in its bounding box, and the objects placed on it so far.

    A blocking cell is legal inside the zone, off the protected web and off `forbid`, or past
    the map edge, where it counts toward nothing. A blocking cell also stands on a terrain the
    identity allows. `impassable` tiles count as walls for
    connectivity. The canvas refuses a placement or a removal that would wall off open ground
    from the protected web."""

    def __init__(self, zone: ZoneRef, model: VegModel, opts: SampleOptions) -> None:
        ts = zone.ts
        self.level: int = zone.level
        self.map_h: int = len(zone.zone_label)
        self.map_w: int = len(zone.zone_label[0])
        self.model: VegModel = model
        self.forbid: AbstractSet[Tile] = opts.forbid
        self.ground: Sequence[Sequence[Terrain]] = opts.ground

        xs = [x for x, _ in ts]
        ys = [y for _, y in ts]
        self.x0: int = min(xs)
        self.y0: int = min(ys)
        self.W: int = max(xs) - self.x0 + 1
        self.H: int = max(ys) - self.y0 + 1
        self.inz: NDArray[np.bool_] = self.box_mask(ts)
        edist = edge_dist(ts)
        self.eb: NDArray[np.int8] = self._edge_bins(ts, edist)

        cx, cy = zone.centroid
        seedt = min(ts, key=lambda t: (t[0] - round(cx)) ** 2 + (t[1] - round(cy)) ** 2)
        prot = opts.prot
        if prot is None:
            prot = protected_web(zone, edist, seedt)
        self.prot: AbstractSet[Tile] = prot
        self.protm: NDArray[np.bool_] = self.box_mask(prot)
        self.solid: NDArray[np.bool_] = self._solid_mask(opts.impassable)
        self.border: NDArray[np.bool_] = self.box_mask(opts.border)

        self.tiles: list[Tile] = sorted(ts)
        self.Nt: int = len(self.tiles)
        self.tiles_per_ebin: NDArray[np.int64] = np.bincount(
            self.eb[self.inz].ravel(), minlength=EBINS
        )

        self.blkcnt: NDArray[np.int32] = np.zeros((self.H, self.W), dtype=np.int32)
        self.objs: list[tuple[int, int, int, int]] = []
        self.nblocked: int = 0

    def box_mask(self, tiles: Collection[Tile]) -> NDArray[np.bool_]:
        m: NDArray[np.bool_] = np.zeros((self.H, self.W), dtype=np.bool_)
        for x, y in tiles:
            if 0 <= x - self.x0 < self.W and 0 <= y - self.y0 < self.H:
                m[y - self.y0, x - self.x0] = True
        return m

    def _edge_bins(self, ts: AbstractSet[Tile], edist: Mapping[Tile, int]) -> NDArray[np.int8]:
        eb: NDArray[np.int8] = np.zeros((self.H, self.W), dtype=np.int8)
        for x, y in ts:
            eb[y - self.y0, x - self.x0] = min(edist[(x, y)], EBINS - 1)
        return eb

    def _solid_mask(self, impassable: AbstractSet[Tile]) -> NDArray[np.bool_]:
        solid: NDArray[np.bool_] = np.logical_not(self.inz)
        return solid | self.box_mask(impassable)

    def on_map(self, x: int, y: int) -> bool:
        return 0 <= x < self.map_w and 0 <= y < self.map_h

    def blocked_cells(self, c: int, ii: int, x: int, y: int) -> list[Tile] | None:
        """Absolute blocking cells of ident ii of category c anchored at (x,y); None = illegal."""
        x0, y0, W, H = self.x0, self.y0, self.W, self.H
        inz, protm, forbid, model = self.inz, self.protm, self.forbid, self.model
        ground, land = self.ground, model.iland[c][ii]
        cells: list[Tile] = []
        for dx, dy in model.iblk[c][ii]:
            bx, by = x + dx, y + dy
            if not self.on_map(bx, by):
                continue
            lx, ly = bx - x0, by - y0
            if (
                not (0 <= lx < W and 0 <= ly < H)
                or not inz[ly, lx]
                or protm[ly, lx]
                or (bx, by) in forbid
                or (ground and ground[by][bx] not in land)
            ):
                return None
            cells.append((bx, by))
        if any((x + dx, y + dy) in forbid for dx, dy in model.ifoot[c][ii]):
            return None
        return cells

    def _local(self, cells: list[Tile]) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
        xs = np.array([bx - self.x0 for bx, _ in cells], dtype=np.int64)
        ys = np.array([by - self.y0 for _, by in cells], dtype=np.int64)
        return xs, ys

    def _placed_cells(self, c: int, ii: int, x: int, y: int) -> list[Tile]:
        return [
            (x + dx, y + dy) for dx, dy in self.model.iblk[c][ii] if self.on_map(x + dx, y + dy)
        ]

    def try_place(self, obj: tuple[int, int, int, int], cells: list[Tile]) -> bool:
        """Record `obj` as (x, y, category, identity) and block its `cells`, unless that walls
        off open ground. Whether it was placed."""
        if not keeps_connected(self.solid, self.protm, self.blkcnt, *self._local(cells)):
            return False
        x0, y0, blkcnt = self.x0, self.y0, self.blkcnt
        self.objs.append(obj)
        for bx, by in cells:
            blkcnt[by - y0, bx - x0] += 1
            if blkcnt[by - y0, bx - x0] == 1:
                self.nblocked += 1
        return True

    def try_remove(self, j: int) -> bool:
        """Remove the `j`-th object and free its cells, unless a freed tile would sit walled
        off from the web. The last object takes its index. Whether it was removed."""
        x0, y0, blkcnt, objs = self.x0, self.y0, self.blkcnt, self.objs
        x, y, c, ii = objs[j]
        cells = self._placed_cells(c, ii, x, y)
        if not frees_connected(self.solid, self.protm, self.blkcnt, *self._local(cells)):
            return False
        objs[j] = objs[-1]
        _ = objs.pop()
        for tx, ty in cells:
            bx, by = tx - x0, ty - y0
            blkcnt[by, bx] -= 1
            if blkcnt[by, bx] == 0:
                self.nblocked -= 1
        return True

    def result(self) -> ZoneGrowth:
        """The placed objects in row order, the blocked tiles and the protected web."""
        x0, y0 = self.x0, self.y0
        out: list[PlacedObject] = []
        for x, y, c, ii in sorted(self.objs, key=lambda o: (o[1], o[0])):
            ident = self.model.idents[c][ii]
            out.append(PlacedObject.at(ident, (x, y), level=self.level, purpose=""))
        nz_y, nz_x = self.blkcnt.nonzero()
        ys_nz = cast(list[int], nz_y.tolist())
        xs_nz = cast(list[int], nz_x.tolist())
        blocked = {(x0 + lx, y0 + ly) for ly, lx in zip(ys_nz, xs_nz, strict=True)}
        return out, blocked, self.prot

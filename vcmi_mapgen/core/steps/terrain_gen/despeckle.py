"""Despeckle: merge terrain slivers into the terrain around them, so generated terrain
reads as coherent regions and does not fragment the map into unplayable sliver zones."""

import collections
from collections.abc import Collection
from dataclasses import dataclass
from typing import cast

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.model.terrain import Terrain

MIN_TERRAIN_PATCH = 4
"""A patch, which becomes a zone, keeps its terrain with more than this many tiles, or with
exactly this many in a compact 2x2 square. Anything smaller, and every narrow four-tile
shape, merges into its dominant land neighbour. Hardcoded, not mined."""

_NB4 = ((1, 0), (-1, 0), (0, 1), (0, -1))


def _thin_tiles(ids: list[list[int]], thin_drawable: Collection[int]) -> list[Tile]:
    """Tiles of a terrain outside ``thin_drawable`` that belong to no 2x2 same-terrain
    square. Off-map tiles count as the same terrain, as the tiler reads them."""
    grid = np.array(ids, dtype=np.int64)
    padded = np.pad(grid, 1, constant_values=-1)
    a, b, c, d = padded[:-1, :-1], padded[1:, :-1], padded[:-1, 1:], padded[1:, 1:]
    top = np.maximum(np.maximum(a, b), np.maximum(c, d))
    square = np.logical_and(
        np.logical_and(_blank_or(a, top), _blank_or(b, top)),
        np.logical_and(_blank_or(c, top), _blank_or(d, top)),
    )
    thick = np.logical_or(
        np.logical_or(square[:-1, :-1], square[1:, :-1]),
        np.logical_or(square[:-1, 1:], square[1:, 1:]),
    )
    thin = np.logical_and(np.logical_not(thick), np.isin(grid, list(thin_drawable), invert=True))
    ys, xs = np.nonzero(thin)
    return list(zip(cast(list[int], xs.tolist()), cast(list[int], ys.tolist()), strict=True))


def _blank_or(corner: NDArray[np.int64], top: NDArray[np.int64]) -> NDArray[np.bool_]:
    return np.logical_or(np.equal(corner, -1), np.equal(corner, top))


def keep_patch(tiles: Collection[Tile], min_patch: int = MIN_TERRAIN_PATCH) -> bool:
    """Shape-aware keep rule: more than ``min_patch`` tiles always stays; exactly ``min_patch``
    stays only when compact (bounding box 2x2 — for 4 tiles that forces the full square, the
    one 4-tile shape that isn't a narrow sliver); anything smaller is absorbed."""
    if len(tiles) > min_patch:
        return True
    if len(tiles) == min_patch:
        xs = [x for x, _ in tiles]
        ys = [y for _, y in tiles]
        return max(xs) - min(xs) == 1 and max(ys) - min(ys) == 1
    return False


@dataclass(frozen=True, slots=True)
class _Despeckler:
    ids: list[list[int]]
    thin_drawable: Collection[int]
    min_patch: int
    protect: Collection[Tile]

    def components(self) -> list[tuple[list[Tile], int]]:
        ids = self.ids
        H, W = len(ids), len(ids[0])
        comp = [[-1] * W for _ in range(H)]
        comps: list[tuple[list[Tile], int]] = []
        cid = 0
        for y in range(H):
            for x in range(W):
                if comp[y][x] >= 0:
                    continue
                t = ids[y][x]
                stack, tiles = [(x, y)], [(x, y)]
                comp[y][x] = cid
                while stack:
                    a, b = stack.pop()
                    for dx, dy in _NB4:
                        nx, ny = a + dx, b + dy
                        if 0 <= nx < W and 0 <= ny < H and comp[ny][nx] < 0 and ids[ny][nx] == t:
                            comp[ny][nx] = cid
                            stack.append((nx, ny))
                            tiles.append((nx, ny))
                comps.append((tiles, t))
                cid += 1
        return comps

    def dominant_neighbour(self, tiles: list[Tile], t: int) -> int | None:
        ids = self.ids
        H, W = len(ids), len(ids[0])
        nbr_land: collections.Counter[int] = collections.Counter()
        nbr_all: collections.Counter[int] = collections.Counter()
        for x, y in tiles:
            for dx, dy in _NB4:
                nx, ny = x + dx, y + dy
                if 0 <= nx < W and 0 <= ny < H and ids[ny][nx] != t:
                    nbr_all[ids[ny][nx]] += 1
                    if Terrain(ids[ny][nx]).is_land:
                        nbr_land[ids[ny][nx]] += 1
        nbr = nbr_land or nbr_all
        if nbr:
            return nbr.most_common(1)[0][0]
        return None

    def absorb_patches(self) -> bool:
        changed = False
        for tiles, t in self.components():
            if keep_patch(tiles, self.min_patch) or any(tp in self.protect for tp in tiles):
                continue
            newt = self.dominant_neighbour(tiles, t)
            if newt is not None:
                for x, y in tiles:
                    self.ids[y][x] = newt
                changed = True
        return changed

    def erode_thin(self) -> bool:
        changed = False
        for x, y in _thin_tiles(self.ids, self.thin_drawable):
            if (x, y) in self.protect:
                continue
            newt = self.dominant_neighbour([(x, y)], self.ids[y][x])
            if newt is not None:
                self.ids[y][x] = newt
                changed = True
        return changed


def despeckle(
    ids: list[list[int]],
    thin_drawable: Collection[Terrain],
    protect: Collection[Tile] = (),
    min_patch: int = MIN_TERRAIN_PATCH,
) -> list[list[Terrain]]:
    """Reassign every connected same-terrain patch failing ``keep_patch``, and every tile
    outside ``thin_drawable`` in no 2x2 same-terrain square, to the land terrain it borders
    most. Water or rock takes it only when no land borders it, so a sliver enclosed by
    barriers becomes barrier. It repeats until no small patch or thin tile remains, since a
    merge can expose new ones. ``protect`` tiles are never merged: an underground tunnel can
    flank rock on both long sides, and a short stretch of it would otherwise out-vote to rock
    and sever a connection the generator built on purpose."""
    work = [row[:] for row in ids]
    despeckler = _Despeckler(work, frozenset(int(t) for t in thin_drawable), min_patch, protect)
    for _ in range(24):
        patched = despeckler.absorb_patches()
        thinned = despeckler.erode_thin()
        if not (patched or thinned):
            break
    return [[Terrain(t) for t in row] for row in work]

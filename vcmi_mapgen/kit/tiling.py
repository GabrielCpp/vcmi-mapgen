"""Corpus-learned terrain auto-tiler: a terrain-id grid -> a faithful cell grid with
H3-correct transition VIEWS (+ the `m` mirror flag), not a flat clean frame. We learn,
per (centre terrain, its 8 neighbour terrains), the (view, m) pairs real maps use, then
replay them — reproducing shores, beaches and land-land blends exactly as the editor
draws them. Back-off: exact 8-sig -> 4-sig (N,W,E,S) -> flat clean view.

Tiny terrain speckles are despeckled first (merged into their dominant neighbour) so
generated terrain reads as coherent regions rather than fragmenting into unplayable
sliver-zones.
"""

import collections
import functools
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from pathlib import Path

from vcmi_mapgen.core.model import Cell, JsonValue, MapState, Tile
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.kit import pp_cache
from vcmi_mapgen.vcmi.formats import json_value as jv

TILER_SOURCE = "vcmi_mapgen.kit.tiling.learn_terrain_tiler"

type ViewMirror = tuple[int, int]
type Tiler = tuple[
    dict[tuple[int, tuple[int, ...]], collections.Counter[ViewMirror]],
    dict[tuple[int, tuple[int, ...]], collections.Counter[ViewMirror]],
    dict[int, collections.Counter[ViewMirror]],
]

# Per-terrain CLEAN interior tile views (corpus-derived: the views real maps use on
# tiles whose 4 neighbours are the same terrain). Synthetic views 0-7 land on
# transition/border frames for most terrains, which renders as an "off"/patchy
# ground — restricting to these keeps generated terrain reading as flat ground.
CLEAN_VIEWS: dict[int, list[int]] = {
    0: [21, 22, 23, 24, 25, 26, 27, 28, 29],  # dirt
    1: [0, 1, 2, 3, 4, 5, 6, 7],  # sand
    2: [49, 50, 51, 52, 53, 54, 55, 56],  # grass
    3: [49, 50, 51, 52, 53, 54, 55, 56],  # snow
    4: [49, 50, 51, 52, 53, 54, 55, 56],  # swamp
    5: [49, 50, 51, 52, 53, 54, 55, 56],  # rough
    6: [49, 50, 51, 52, 53, 54, 55, 56],  # subterr
    7: [49, 50, 51, 52, 53, 54, 55, 56],  # lava
    8: [21, 22, 23, 24, 25, 26, 27, 28, 29],  # water
    9: [0, 1, 2, 3, 4, 5, 6, 7],  # rock
}


def _cell(t: int, x: int = 0, y: int = 0) -> Cell:
    # vary the terrain view-frame per tile (deterministic) across the CLEAN center
    # variants for this terrain, so painted ground reads as flat ground (not a
    # repeated tile, and not transition/border frames).
    vs = CLEAN_VIEWS.get(t, [49, 50, 51, 52, 53, 54, 55, 56])
    return Cell(t=t, view=vs[(x * 7 + y * 13) % len(vs)])


_N8 = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]


def _neigh8(grid: list[list[int]], x: int, y: int, W: int, H: int) -> tuple[int, ...]:
    t = grid[y][x]
    return tuple(
        grid[y + dy][x + dx] if 0 <= x + dx < W and 0 <= y + dy < H else t for dx, dy in _N8
    )


def learn_terrain_tiler(maps: Iterable[MapState]) -> Tiler:
    """(exact, four, clean) view/m tables learned from every corpus terrain tile."""
    exact: dict[tuple[int, tuple[int, ...]], collections.Counter[ViewMirror]] = (
        collections.defaultdict(collections.Counter)
    )  # (t, sig8)        -> (view,m)
    four: dict[tuple[int, tuple[int, ...]], collections.Counter[ViewMirror]] = (
        collections.defaultdict(collections.Counter)
    )  # (t, N,W,E,S)     -> (view,m)
    clean: dict[int, collections.Counter[ViewMirror]] = collections.defaultdict(
        collections.Counter
    )  # t (all-same nbrs)-> (view,m)
    for fm in maps:
        for g in fm.cells.values():
            H = len(g)
            W = len(g[0])
            T = [[c.t for c in row] for row in g]
            for y in range(H):
                for x in range(W):
                    c = g[y][x]
                    t = c.t
                    vm = (c.view, c.m)
                    sig = _neigh8(T, x, y, W, H)
                    exact[(t, sig)][vm] += 1
                    four[(t, (sig[1], sig[3], sig[4], sig[6]))][vm] += 1
                    if all(v == t for v in sig):
                        clean[t][vm] += 1
    return (exact, four, clean)


def _counts_to_json(counter: collections.Counter[ViewMirror]) -> list[list[int]]:
    return [[view, m, n] for (view, m), n in counter.items()]


def _counts_from_json(raw: JsonValue) -> collections.Counter[ViewMirror]:
    counter = collections.Counter[ViewMirror]()
    for entry in jv.as_list(raw):
        view, m, n = (jv.as_int(v) for v in jv.as_list(entry))
        counter[(view, m)] = n
    return counter


def _sig_table_from_json(
    raw: JsonValue,
) -> dict[tuple[int, tuple[int, ...]], collections.Counter[ViewMirror]]:
    table: dict[tuple[int, tuple[int, ...]], collections.Counter[ViewMirror]] = {}
    for entry in jv.as_list(raw):
        t, sig, counts = jv.as_list(entry)
        key = (jv.as_int(t), tuple(jv.as_int(v) for v in jv.as_list(sig)))
        table[key] = _counts_from_json(counts)
    return table


def tiler_path() -> Path:
    return pp_cache.PP_DIR / "tiler.json"


def save_tiler(tiler: Tiler) -> None:
    exact, four, clean = tiler
    pp_cache.write(
        tiler_path(),
        TILER_SOURCE,
        {
            "exact": [[t, list(sig), _counts_to_json(c)] for (t, sig), c in exact.items()],
            "four": [[t, list(sig), _counts_to_json(c)] for (t, sig), c in four.items()],
            "clean": [[t, _counts_to_json(c)] for t, c in clean.items()],
        },
    )


@functools.cache
def load_tiler() -> Tiler:
    raw = pp_cache.read(tiler_path())
    clean: dict[int, collections.Counter[ViewMirror]] = {}
    for entry in jv.as_list(raw.get("clean")):
        t, counts = jv.as_list(entry)
        clean[jv.as_int(t)] = _counts_from_json(counts)
    return (
        _sig_table_from_json(raw.get("exact")),
        _sig_table_from_json(raw.get("four")),
        clean,
    )


def _tile_cell(t: int, sig: tuple[int, ...], x: int, y: int, tiler: Tiler) -> Cell:
    exact, four, clean = tiler
    if all(v == t for v in sig):  # interior: vary for texture
        cc = clean.get(t)
        if cc:
            opts = [vm for vm, _ in cc.most_common(8)]
            view, mm = opts[(x * 7 + y * 13) % len(opts)]
            return Cell(t=t, view=view, m=mm)
        return _cell(t, x, y)
    hit = exact.get((t, sig)) or four.get((t, (sig[1], sig[3], sig[4], sig[6])))
    if not hit:  # unseen border config: flat fallback
        return _cell(t, x, y)
    view, mm = hit.most_common(1)[0][0]  # the H3-correct transition frame
    return Cell(t=t, view=view, m=mm)


MIN_TERRAIN_PATCH = 4  # a patch (= future zone) must have more than this many tiles, EXCEPT a
#                         compact 2x2 square which is still a fine zone; anything smaller or a
#                         4-tile narrow shape (1x4 line, L/S/T tetromino) is merged into the
#                         dominant LAND neighbour, so terrain reads as coherent regions (and
#                         doesn't fragment the map into unplayable sliver-zones).

# Terrains that legitimately occur 1-tile-wide in the corpus, exempt from thin-shape erosion:
# dirt and sand are H3's base terrains (the NEIGHBOUR draws the transition on its own tile, a
# base tile always renders clean), and subterranean is the underground tunnel terrain (real
# undergrounds are full of 1-wide tunnels, so the tiler knows their signatures). Corpus interior
# rates of no-2x2 tiles: dirt 0.065%, sand 0.59%, subterranean 0.45% — vs ~0.00% for everything
# else (grass/snow/swamp/rough/lava/water/rock), whose transition tilesets cannot draw a 1-wide
# shape at all: an unseen signature makes _tile_cell fall back to a flat clean tile, rendering
# an abrupt untransitioned square (e.g. a lone white "snow hole" in the middle of dirt).
_EROSION_EXEMPT = frozenset({0, 1, 6})  # dirt, sand, subterranean


def _thin_tiles(ids: list[list[int]], W: int, H: int) -> list[Tile]:
    """Tiles of a non-exempt terrain that belong to NO 2x2 same-terrain square. Off-map cells
    count as same terrain, mirroring ``_neigh8``, so map-edge tiles get the natural treatment."""

    def same(xs: int, ys: int, t: int) -> bool:
        return not (0 <= xs < W and 0 <= ys < H) or ids[ys][xs] == t

    thin: list[Tile] = []
    for y in range(H):
        for x in range(W):
            t = ids[y][x]
            if t in _EROSION_EXEMPT:
                continue
            if not any(
                all(same(xs + dx, ys + dy, t) for dx in (0, 1) for dy in (0, 1))
                for xs in (x - 1, x)
                for ys in (y - 1, y)
            ):
                thin.append((x, y))
    return thin


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


_NB4 = ((1, 0), (-1, 0), (0, 1), (0, -1))


@dataclass(frozen=True, slots=True)
class _Despeckler:
    ids: list[list[int]]
    W: int
    H: int
    min_patch: int
    protect: Collection[Tile]

    def components(self) -> list[tuple[list[Tile], int]]:
        ids, W, H = self.ids, self.W, self.H
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
        ids, W, H = self.ids, self.W, self.H
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
        for x, y in _thin_tiles(self.ids, self.W, self.H):
            if (x, y) in self.protect:
                continue
            newt = self.dominant_neighbour([(x, y)], self.ids[y][x])
            if newt is not None:
                self.ids[y][x] = newt
                changed = True
        return changed


def despeckle_ids(
    ids: list[list[int]],
    W: int,
    H: int,
    min_patch: int = MIN_TERRAIN_PATCH,
    protect: Collection[Tile] = (),
) -> list[list[int]]:
    """Reassign every connected same-terrain patch failing ``keep_patch`` — and every
    non-exempt tile in no 2x2 same-terrain square (``_thin_tiles``: 1-wide tendrils, necks
    and inlets H3's transition tilesets cannot draw) — to the LAND terrain it borders most
    (water/rock only when no land borders it — a sliver enclosed by barriers becomes
    barrier), iterating until no small patch or thin tile remains (a merge can expose new
    ones). `protect` cells are never merged: a thin corridor (e.g. an underground tunnel)
    can flank rock on both long sides, so a short same-id stretch along it would otherwise
    out-vote to rock and sever a connection the generator built on purpose."""
    ids = [row[:] for row in ids]
    despeckler = _Despeckler(ids, W, H, min_patch, protect)
    for _ in range(24):
        patched = despeckler.absorb_patches()
        thinned = despeckler.erode_thin()
        if not (patched or thinned):
            break
    return ids


def tile_terrain(
    id_grid: list[list[int]], W: int, H: int, protect: Collection[Tile] = ()
) -> list[list[Cell]]:
    """Terrain-id grid -> faithful cell grid with corpus-correct transition views. Tiny terrain
    speckles (< MIN_TERRAIN_PATCH tiles) are first merged into their dominant neighbour;
    `protect` cells are exempt (see `despeckle_ids`)."""
    id_grid = despeckle_ids(id_grid, W, H, protect=protect)
    tiler = load_tiler()
    return [
        [_tile_cell(id_grid[y][x], _neigh8(id_grid, x, y, W, H), x, y, tiler) for x in range(W)]
        for y in range(H)
    ]

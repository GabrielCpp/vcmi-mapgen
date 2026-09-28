"""Macro terrain model (L0) — capacity-constrained zone growth + boundary texturing (spec §4).

The causal 3-tile Markov chain (`markov`) reproduces border texture but its patch sizes
decay geometrically — generated maps segment into many small fragments, while corpus maps hold a
handful of LARGE designed regions. This module plans the macro structure first:

  1. **mine**   — corpus macro statistics: zone-area distribution, per-terrain area shares,
                  terrain adjacency mix, water fraction (cached in ``data/pp/macro_stats.json``).
  2. **plan**   — sample a water mask (low-frequency noise at the corpus water quantile), draw
                  zone target AREAS from the corpus distribution (scaled to fill the land),
                  spread seeds, and assign terrains by Metropolis on the seed k-NN graph with
                  energy -log A[t_i][t_j] (adjacent zones prefer corpus-frequent terrain pairs;
                  same-terrain contact is corpus-impossible, so it is strongly repelled).
  3. **grow**   — capacity-constrained multi-source Dijkstra with jittered costs: each zone
                  claims tiles by increasing noisy distance until it reaches its target area —
                  the corpus zone-size distribution is imposed BY CONSTRUCTION, with organic
                  (non-Voronoi) borders.
  4. **texture**— the Markov chain demoted to where it is good: isotropic Gibbs sweeps
                  RESTRICTED to a 2-tile band around zone borders (interiors clamped), so
                  boundaries get corpus transition texture and interiors can never fragment.

    uv run python -m vcmi_mapgen.core.steps.terrain_gen.macro_topo --seed 3 --size 72
"""

import argparse
import collections
import heapq
import math
import os
import random
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from vcmi_mapgen.core.grid.noise import value_noise
from vcmi_mapgen.core.grid.segment import segment_level
from vcmi_mapgen.core.model import Cell, JsonValue, Tile
from vcmi_mapgen.core.steps.terrain_gen import markov as MT
from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.kit import pp_cache
from vcmi_mapgen.kit.paths import project_root
from vcmi_mapgen.kit.render_palette import TERRAIN_RGB
from vcmi_mapgen.kit.render_palette import TERRAIN_TILE_PX as _TILE
from vcmi_mapgen.vcmi.formats import json_value

ROOT = project_root()
STATS_PATH = str(ROOT / "data" / "pp" / "macro_stats.json")
STATS_PATH_UNDERGROUND = str(ROOT / "data" / "pp" / "macro_stats_underground.json")
SOURCE = "vcmi_mapgen.core.steps.terrain_gen.macro_topo.mine_macro"
WATER, ROCK = 8, 9
MIN_ZONE_AREA = 40  # floor for sampled target areas
JITTER = 1.4  # growth-cost noise amplitude (0 = pure Voronoi-like fronts)
BAND = 2  # boundary-texturing band half-width (tiles)


@dataclass(slots=True)
class MacroStats:
    areas: list[int]
    barrier_fracs: list[float]
    terr_share: dict[int, int]
    adj: dict[str, int]
    nzones: list[int]


@dataclass(frozen=True, slots=True)
class MacroReport:
    zones: int
    big_zones: int
    big_share: float


def _as_float(value: JsonValue) -> float:
    return float(value) if isinstance(value, int | float) else 0.0


def _stats_from_json(raw: JsonValue) -> MacroStats:
    obj = json_value.as_object(raw)
    return MacroStats(
        areas=[json_value.as_int(v) for v in json_value.as_list(obj.get("areas"))],
        barrier_fracs=[_as_float(v) for v in json_value.as_list(obj.get("barrier_fracs"))],
        terr_share={
            int(k): json_value.as_int(v)
            for k, v in json_value.as_object(obj.get("terr_share")).items()
        },
        adj={k: json_value.as_int(v) for k, v in json_value.as_object(obj.get("adj")).items()},
        nzones=[json_value.as_int(v) for v in json_value.as_list(obj.get("nzones"))],
    )


def _stats_to_json(st: MacroStats) -> dict[str, object]:
    return {
        "areas": st.areas,
        "barrier_fracs": st.barrier_fracs,
        "terr_share": {str(k): v for k, v in st.terr_share.items()},
        "adj": st.adj,
        "nzones": st.nzones,
    }


# ---------------------------------------------------------------------------
# 1. corpus macro statistics
# ---------------------------------------------------------------------------


def _mine_zones(
    lvl: list[list[Cell]], areas: list[int], terr_share: collections.Counter[int]
) -> int:
    zones, _, _ = segment_level(lvl)
    big = 0
    for z in zones.values():
        t = z.terrain_type
        if 0 <= t < 8:
            areas.append(z.area)
            terr_share[t] += z.area
            if z.area >= 60:
                big += 1
    return big


def _mine_adjacency(T: list[list[int]], W: int, H: int, adj: collections.Counter[str]) -> None:
    for y in range(H):
        for x in range(W):
            a = T[y][x]
            for dx, dy in ((1, 0), (0, 1)):
                if x + dx < W and y + dy < H:
                    b = T[y + dy][x + dx]
                    if a != b and 0 <= a < 8 and 0 <= b < 8:
                        adj[f"{min(a, b)}|{max(a, b)}"] += 1


def mine_macro(level: int, maps: Iterable[OR.FaithfulMap]) -> MacroStats:
    """Corpus macro stats for terrain level `level` (0 = surface, 1 = underground). The
    underground table is mined independently from `fm["terrain"][1]` of two-level corpus
    maps — real underground zone areas/adjacency/barrier fraction are statistically distinct
    from the surface (rock, not subterr, is the dominant barrier terrain there; see corpus
    histograms in the design notes), so it is never derived from or blended with level-0 stats."""
    barrier = WATER if level == 0 else ROCK
    areas: list[int] = []
    barrier_fracs: list[float] = []
    terr_share = collections.Counter[int]()
    adj = collections.Counter[str]()  # "t1|t2" boundary-tile counts, t1 <= t2
    nzones: list[int] = []
    for fm in maps:
        if level >= len(fm.terrain):
            continue
        lvl = fm.terrain[level]
        H = len(lvl)
        W = len(lvl[0]) if H else 0
        T = [[c.t for c in row] for row in lvl]
        nb = sum(1 for row in T for t in row if t == barrier)
        barrier_fracs.append(nb / max(W * H, 1))
        nzones.append(_mine_zones(lvl, areas, terr_share))
        _mine_adjacency(T, W, H, adj)
    st = MacroStats(
        areas=sorted(areas),
        barrier_fracs=sorted(barrier_fracs),
        terr_share=dict(terr_share),
        adj=dict(adj),
        nzones=nzones,
    )
    return st


def _stats_path(level: int) -> Path:
    return Path(STATS_PATH if level == 0 else STATS_PATH_UNDERGROUND)


def load_macro(level: int = 0) -> MacroStats:
    return _stats_from_json(pp_cache.read(_stats_path(level)))


def save_macro(level: int, st: MacroStats) -> None:
    pp_cache.write(_stats_path(level), SOURCE, _stats_to_json(st))


# ---------------------------------------------------------------------------
# 2. plan: water, areas, seeds, terrain assignment
# ---------------------------------------------------------------------------


def _water_mask(
    W: int, H: int, frac: float, rng: random.Random, cell: int | None = None
) -> list[list[bool]]:
    """Coherent water blobs: value noise thresholded at the `frac` quantile. `cell` sets the
    noise wavelength — large (default) gives seas/lakes, small fragments land into islands."""
    if frac <= 0.01:
        return [[False] * W for _ in range(H)]
    noise = value_noise(W, H, cell or max(6, min(W, H) // 5), rng)
    flat = sorted(v for row in noise for v in row)
    thr = flat[int(frac * (len(flat) - 1))]
    return [[noise[y][x] <= thr for x in range(W)] for y in range(H)]


def carve_corridor(
    land: list[list[bool]],
    span: tuple[Tile, Tile],
    rng: random.Random,
    half_w: int = 1,
    protect: set[Tile] | None = None,
) -> None:
    """Drunken walk from `a` toward `b`, marking a `half_w`-radius band as land — a tunnel,
    not a straight line, so it reads as a cave passage rather than a ruler-drawn corridor.
    Cells are also added to `protect` (if given): a thin corridor sits entirely inside the
    boundary-texturing band on both sides, so without protection `_texture_boundaries`'s
    Gibbs resampling — drawing from a rock-heavy corpus conditional — can erode the whole
    tunnel back to rock, disconnecting caverns `_tunnel_mask` had genuinely joined."""
    a, b = span
    H = len(land)
    W = len(land[0])
    x, y = float(a[0]), float(a[1])
    bx, by = b
    for _ in range(8 * (abs(a[0] - bx) + abs(a[1] - by)) + 40):
        ix, iy = round(x), round(y)
        for dy in range(-half_w, half_w + 1):
            for dx in range(-half_w, half_w + 1):
                nx, ny = ix + dx, iy + dy
                if 0 <= nx < W and 0 <= ny < H:
                    land[ny][nx] = True
                    if protect is not None:
                        protect.add((nx, ny))
        if (ix, iy) == (bx, by):
            break
        ddx, ddy = bx - x, by - y
        dist = max(math.pow(ddx**2 + ddy**2, 0.5), 1e-6)
        x += ddx / dist * 0.8 + rng.uniform(-0.6, 0.6)
        y += ddy / dist * 0.8 + rng.uniform(-0.6, 0.6)
        x = min(max(x, 1.0), W - 2.0)
        y = min(max(y, 1.0), H - 2.0)


def _tunnel_mask(
    W: int, H: int, land_frac: float, rng: random.Random
) -> tuple[list[list[bool]], set[Tile]]:
    """Connected cavern+tunnel land mask for the underground level: a handful of organic
    cavern blobs joined by random-walk corridors (a minimum-spanning-tree over cavern
    centers, so every cavern is reachable on foot), rather than reusing the surface's
    water-mask (noise thresholded at a quantile) which produces a scattered archipelago —
    correct for open water, wrong for rock: rock is a WALL, not something a hero swims
    across, so an underground level built the same way as a sea strands every cavern in
    its own sealed pocket. This shape instead matches the user's description of real H3
    undergrounds: tunnels leading to larger patches, not islands."""
    budget = max(1, round(land_frac * W * H))
    n_caverns = max(3, min(8, budget // 90))
    centers = _cavern_centers(W, H, n_caverns, rng)

    noise = value_noise(W, H, 5, rng)
    land = [[False] * W for _ in range(H)]
    protect: set[Tile] = set()
    avg_r = max(3.0, math.pow(budget / max(n_caverns, 1) / math.pi, 0.5) * 0.7)
    for cx, cy in centers:
        r = avg_r * rng.uniform(0.7, 1.4)
        _paint_cavern(land, noise, (cx, cy), r)

    for i, j in _cavern_edges(centers, n_caverns, rng):
        carve_corridor(land, (centers[i], centers[j]), rng, protect=protect)
    return land, protect


def _cavern_centers(W: int, H: int, n_caverns: int, rng: random.Random) -> list[Tile]:
    margin = 6
    centers: list[Tile] = []
    tries = 0
    mind2 = (0.6 * math.pow(W * H / n_caverns, 0.5)) ** 2
    while len(centers) < n_caverns and tries < n_caverns * 300:
        p = (rng.randint(margin, W - margin - 1), rng.randint(margin, H - margin - 1))
        tries += 1
        if all((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 >= mind2 for q in centers):
            centers.append(p)
    while len(centers) < n_caverns:
        centers.append((rng.randint(margin, W - margin - 1), rng.randint(margin, H - margin - 1)))
    return centers


def _paint_cavern(land: list[list[bool]], noise: list[list[float]], center: Tile, r: float) -> None:
    H = len(land)
    W = len(land[0])
    cx, cy = center
    for y in range(max(0, cy - int(r) - 2), min(H, cy + int(r) + 3)):
        for x in range(max(0, cx - int(r) - 2), min(W, cx + int(r) + 3)):
            d = math.pow((x - cx) ** 2 + (y - cy) ** 2, 0.5)
            wobble = r * (0.75 + 0.35 * noise[y][x])
            if d <= wobble:
                land[y][x] = True


def _cavern_edges(centers: list[Tile], n_caverns: int, rng: random.Random) -> list[tuple[int, int]]:
    # MST over cavern centers (nearest-unconnected-first) + a few extra loop edges
    connected = {0}
    remaining = set(range(1, len(centers)))
    edges: list[tuple[int, int]] = []
    while remaining:
        i, j = min(
            ((i, j) for i in connected for j in remaining),
            key=lambda ij: (
                (centers[ij[0]][0] - centers[ij[1]][0]) ** 2
                + (centers[ij[0]][1] - centers[ij[1]][1]) ** 2
            ),
        )
        edges.append((i, j))
        connected.add(j)
        remaining.discard(j)
    for _ in range(max(0, n_caverns // 4)):
        i, j = rng.sample(range(len(centers)), 2)
        if (i, j) not in edges and (j, i) not in edges:
            edges.append((i, j))
    return edges


def _sample_areas(st: MacroStats, budget: int, rng: random.Random) -> list[int]:
    """Zone target areas drawn from the corpus area distribution, scaled to fill `budget`."""
    pool = [a for a in st.areas if a >= MIN_ZONE_AREA]
    tgt: list[int] = []
    while sum(tgt) < budget:
        tgt.append(rng.choice(pool))
    s = budget / sum(tgt)
    tgt = [max(MIN_ZONE_AREA, round(a * s)) for a in tgt]
    return tgt


def _pair_probs(st: MacroStats, lands: list[int]) -> dict[Tile, float]:
    adj_tot = sum(st.adj.values()) or 1
    padj: dict[Tile, float] = {}
    for a in lands:
        for b in lands:
            key = f"{min(a, b)}|{max(a, b)}"
            padj[(a, b)] = (st.adj.get(key, 0) + 0.5) / adj_tot
    return padj


def _knn3(seeds: list[Tile]) -> list[list[int]]:
    n = len(seeds)
    knn: list[list[int]] = []
    for i in range(n):
        d = sorted(
            range(n),
            key=lambda j: (seeds[i][0] - seeds[j][0]) ** 2 + (seeds[i][1] - seeds[j][1]) ** 2,
        )
        knn.append([j for j in d[1:4]])
    return knn


def _assign_terrains(
    seeds: list[Tile], st: MacroStats, rng: random.Random, iters: int = 400
) -> list[int]:
    """Corpus-weighted terrains on the seed 3-NN graph via Metropolis on the adjacency energy
    E = sum_edges -log P_adj(t_i, t_j): corpus-frequent terrain pairs attract, same-terrain
    contact (never observed — same terrains merge into one zone) is strongly repelled."""
    n = len(seeds)
    share = st.terr_share
    lands = sorted(share)
    wsum = sum(share.values())
    padj = _pair_probs(st, lands)
    knn = _knn3(seeds)

    def draw() -> int:
        r = rng.random() * wsum
        acc = 0
        for t in lands:
            acc += share[t]
            if r <= acc:
                return t
        return lands[-1]

    terrs = [draw() for _ in range(n)]

    def node_e(i: int, t: int) -> float:
        return -sum(math.log(padj[(t, terrs[j])]) for j in knn[i])

    for _ in range(iters):
        i = rng.randrange(n)
        t_new = draw()
        if t_new == terrs[i]:
            continue
        dE = node_e(i, t_new) - node_e(i, terrs[i])
        if dE <= 0 or rng.random() < math.exp(-dE):
            terrs[i] = t_new
    return terrs


# ---------------------------------------------------------------------------
# 3. capacity-constrained growth
# ---------------------------------------------------------------------------


def _grow(
    land: list[list[bool]],
    seeds: list[Tile],
    caps: list[int],
    rng: random.Random,
) -> list[list[int]]:
    """Multi-source Dijkstra with jittered costs; a zone stops claiming at its capacity.
    Leftover pockets (all reachable zones full) are attached to the nearest assigned zone."""
    H = len(land)
    W = len(land[0])
    noise = value_noise(W, H, 5, rng)
    cost = [[1.0 + JITTER * (noise[y][x] + 1.0) / 2.0 for x in range(W)] for y in range(H)]
    label = [[-1] * W for _ in range(H)]
    count = [0] * len(seeds)
    heap: list[tuple[float, int, int, int, int]] = []
    cnt = 0
    for i, (sx, sy) in enumerate(seeds):
        heapq.heappush(heap, (0.0, cnt, sx, sy, i))
        cnt += 1
    while heap:
        d, _, x, y, i = heapq.heappop(heap)
        if label[y][x] != -1 or not land[y][x] or count[i] >= caps[i]:
            continue
        label[y][x] = i
        count[i] += 1
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx2, ny2 = x + dx, y + dy
            if 0 <= nx2 < W and 0 <= ny2 < H and land[ny2][nx2] and label[ny2][nx2] == -1:
                heapq.heappush(heap, (d + cost[ny2][nx2], cnt, nx2, ny2, i))
                cnt += 1
    # leftovers: BFS attach to nearest labelled neighbour (capacity soft here)
    q = collections.deque(
        (x, y) for y in range(H) for x in range(W) if land[y][x] and label[y][x] != -1
    )
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx2, ny2 = x + dx, y + dy
            if 0 <= nx2 < W and 0 <= ny2 < H and land[ny2][nx2] and label[ny2][nx2] == -1:
                label[ny2][nx2] = label[y][x]
                q.append((nx2, ny2))
    return label


# ---------------------------------------------------------------------------
# 4. boundary texturing (the Markov chain, clamped to the border band)
# ---------------------------------------------------------------------------


def _border_band(grid: list[list[int]]) -> list[list[bool]]:
    H = len(grid)
    W = len(grid[0])
    band = [[False] * W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            t = grid[y][x]
            if any(
                0 <= x + dx < W and 0 <= y + dy < H and grid[y + dy][x + dx] != t
                for dx in (-1, 0, 1)
                for dy in (-1, 0, 1)
            ):
                for dy in range(-BAND, BAND + 1):
                    for dx in range(-BAND, BAND + 1):
                        if 0 <= x + dx < W and 0 <= y + dy < H:
                            band[y + dy][x + dx] = True
    return band


def _texture_boundaries(
    grid: list[list[int]],
    rng: random.Random,
    sweeps: int = 3,
    level: int = 0,
    protect: Collection[Tile] = (),
) -> list[list[int]]:
    """Isotropic Gibbs sweeps of the learned 4-neighbour terrain conditional, RESTRICTED to
    tiles within BAND (Chebyshev) of a terrain change; everything else is clamped, so the
    interiors keep their planned terrain and only the borders gain corpus transition texture.
    `level` selects which terrain level's corpus transitions to learn from (0 or 1);
    `markov.learn`/`learn4` already filter to maps that have that level. `protect`
    cells (e.g. underground tunnel corridors, which are thin enough to sit entirely inside
    the band on both sides) are excluded from resampling so a rock-heavy corpus conditional
    can't erode a load-bearing connection back into barrier."""
    H = len(grid)
    W = len(grid[0])
    tables = MT.load_tables(level)
    M4 = tables.chain4
    M = tables.chain
    band = _border_band(grid)
    tiles = [
        (x, y)
        for y in range(1, H - 1)
        for x in range(1, W - 1)
        if band[y][x] and (x, y) not in protect
    ]
    for _ in range(sweeps):
        rng.shuffle(tiles)
        for x, y in tiles:
            lf, u = grid[y][x - 1], grid[y - 1][x]
            r, d = grid[y][x + 1], grid[y + 1][x]
            if sum(M4.full[(lf, u, r, d)].values()) >= 10:
                dist = M4.full[(lf, u, r, d)]
            else:
                dist = collections.Counter[int]()
                dist.update(M4.horiz[(lf, r)])
                dist.update(M4.vert[(u, d)])
                if not dist:
                    dist = M.marg
            grid[y][x] = MT.sample(dist, rng)
    return grid


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


def _spread_seeds(land: list[list[bool]], budget: int, n: int, rng: random.Random) -> list[Tile]:
    H = len(land)
    W = len(land[0])
    land_tiles = [(x, y) for y in range(H) for x in range(W) if land[y][x]]
    seeds: list[Tile] = []
    tries = 0
    mind2 = (0.7 * math.pow(budget / max(n, 1), 0.5)) ** 2
    while len(seeds) < n and tries < n * 200:
        p = land_tiles[rng.randrange(len(land_tiles))]
        tries += 1
        if all((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 >= mind2 for q in seeds):
            seeds.append(p)
    while len(seeds) < n:
        seeds.append(land_tiles[rng.randrange(len(land_tiles))])
    return seeds


@dataclass(frozen=True, slots=True)
class MacroOptions:
    water: float | None = None
    texture: bool = True
    water_mode: str = "normal"
    level: int = 0


def generate(
    W: int,
    H: int,
    seed: int = 3,
    options: MacroOptions | None = None,
    protect_out: set[Tile] | None = None,
) -> list[list[int]]:
    """Macro terrain grid (H rows x W cols of terrain ids) for terrain level `level` (0 =
    surface, 1 = underground). `water` overrides the corpus-drawn barrier fraction (water on
    the surface, rock underground); `water_mode` picks the surface water STYLE: 'none' (pure
    land), 'normal' (corpus-drawn seas/lakes), 'islands' (dominant water + finer noise ->
    archipelago) — the underground level always carves its barrier (rock) at a corpus-drawn
    fraction, but as a connected cavern+tunnel network (`_tunnel_mask`), not a water-style
    archipelago: rock is a wall a hero cannot swim past, so undergrounds must stay walkable
    between caverns the way real H3 maps do (tunnels leading to larger patches).
    `protect_out`, if given a set, is updated in-place with the tunnel-corridor cells that
    downstream steps (notably `kit.tiling.tile_terrain`'s despeckle merge) must never
    reassign to a barrier code, or a thin corridor can be eroded back into rock after
    `generate()` already built it connected.
    Deterministic in `seed`."""
    opts = MacroOptions() if options is None else options
    water = opts.water
    water_mode = opts.water_mode
    level = opts.level
    rng = random.Random(seed)
    st = load_macro(level=level)
    barrier = WATER if level == 0 else ROCK
    protect: set[Tile] = set()
    if level == 1:
        rf = rng.choice(st.barrier_fracs) if water is None else water
        land, protect = _tunnel_mask(W, H, 1.0 - rf, rng)
    else:
        if water_mode == "none":
            wf, cell = 0.0, None
        elif water_mode == "islands":
            wf = rng.uniform(0.45, 0.60) if water is None else water
            cell = max(4, min(W, H) // 10)
        else:
            wf = rng.choice(st.barrier_fracs) if water is None else water
            cell = None
        bmask = _water_mask(W, H, wf, rng, cell)
        land = [[not bmask[y][x] for x in range(W)] for y in range(H)]
    budget = sum(1 for row in land for v in row if v)

    caps = _sample_areas(st, budget, rng)
    seeds = _spread_seeds(land, budget, len(caps), rng)
    caps.sort(reverse=True)  # biggest zones get the best-spread seeds
    terrs = _assign_terrains(seeds, st, rng)

    label = _grow(land, seeds, caps, rng)
    grid = [
        [
            barrier if not land[y][x] else terrs[label[y][x]] if label[y][x] >= 0 else terrs[0]
            for x in range(W)
        ]
        for y in range(H)
    ]
    if opts.texture:
        _ = _texture_boundaries(grid, rng, level=level, protect=protect)
    if protect_out is not None:
        protect_out |= protect
    return grid


def report(grid: list[list[int]]) -> MacroReport:
    """Acceptance metrics of §4.3: zone count + share of land area in zones >= 60 tiles."""
    lvl = [[Cell(t=t) for t in row] for row in grid]
    zones, _, _ = segment_level(lvl)
    land_area = sum(z.area for z in zones.values() if 0 <= z.terrain_type < 8)
    big = [z for z in zones.values() if z.area >= 60 and 0 <= z.terrain_type < 8]
    share = sum(z.area for z in big) / max(land_area, 1)
    return MacroReport(zones=len(zones), big_zones=len(big), big_share=round(share, 3))


class _Args(argparse.Namespace):
    seed: int = 3
    size: int = 72
    water: float | None = None
    level: int = 0


def main() -> None:
    ap = argparse.ArgumentParser()
    _ = ap.add_argument("--seed", type=int, default=3)
    _ = ap.add_argument("--size", type=int, default=72)
    _ = ap.add_argument("--water", type=float, default=None)
    _ = ap.add_argument("--level", type=int, default=0, help="0=surface, 1=underground")
    args = ap.parse_args(namespace=_Args())
    st = load_macro(level=args.level)
    barrier_name = "water" if args.level == 0 else "rock"
    median_area = st.areas[len(st.areas) // 2]
    median_frac = st.barrier_fracs[len(st.barrier_fracs) // 2]
    head = f"macro stats (level {args.level}): {len(st.areas)} corpus zones"
    tail = f"median area {median_area}, median {barrier_name} frac {median_frac:.2f}"
    print(f"{head}, {tail}")
    grid = generate(
        args.size,
        args.size,
        seed=args.seed,
        options=MacroOptions(water=args.water, level=args.level),
    )
    print("generated:", report(grid))
    img = Image.new("RGB", (args.size * _TILE, args.size * _TILE))
    for y, row in enumerate(grid):
        for x, t in enumerate(row):
            box = (x * _TILE, y * _TILE, (x + 1) * _TILE, (y + 1) * _TILE)
            img.paste(TERRAIN_RGB.get(t, (0, 0, 0)), box)
    out = str(ROOT / "out" / "render" / "pp" / f"macro_s{args.seed}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out)
    print("->", out)


if __name__ == "__main__":
    main()

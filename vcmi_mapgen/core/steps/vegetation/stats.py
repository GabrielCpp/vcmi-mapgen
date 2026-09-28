"""Corpus vegetation statistics for the marked-point-process layer (spec M0).

Implements docs/specs/marked-point-process-generation.md §2.5-2.6: one pass over the corpus
extracts, per terrain, the DECORATION anchor pattern —

  - first-order intensity  lam[cat][edge_bin]   (anchors per tile, by distance-to-rim bin),
  - multitype pair correlation  g[a][b][r]      (Chebyshev rings r = 0..RMAX; r=0 measures how
    often footprints STACK — overlap is corpus-legal for vegetation, so it is learned, not banned),
  - the mark mix              anim_w[cat][anim] (corpus frequency of each sprite within a category
    — identity itself always resolves through the catalog, the corpus contributes counts only),
  - the budget target         veg_blocked_frac  (fraction of zone tiles under a decoration's
    blocking cell — the Boolean-model coverage the sampler must reproduce),
  - corpus run-length histogram of the veg-only open field (the M1 validation yardstick).

Categories are the catalog's decoration types (`Catalog.decor_category`); water features
are dropped everywhere. Cached per terrain in
``data/pp/veg_<terrain>.json``.

    uv run python -m vcmi_mapgen.core.steps.vegetation.stats --report grass
"""

import argparse
import collections
import math
from collections.abc import Callable, Collection, Iterable, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.geometry import EBINS, edge_dist, run_lengths
from vcmi_mapgen.core.grid.segment import segment_level
from vcmi_mapgen.core.model import Footprint, JsonValue, MapState, Role, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.kit import pp_cache
from vcmi_mapgen.kit.paths import project_root
from vcmi_mapgen.vcmi.formats import json_value

ROOT = project_root()
PP_DIR = str(ROOT / "data" / "pp")
SOURCE = "vcmi_mapgen.core.steps.vegetation.stats.mine"
RMAX = 6  # pair-correlation rings 0..RMAX (Chebyshev)
MIN_AREA = 60  # same zone-size floor as the field learner
CELL = 6  # coarse-cell size for the overdispersion (Cox field) statistic


@dataclass(frozen=True, slots=True)
class CellStats:
    size: int
    n: int
    sum: int
    sum2: int


@dataclass(slots=True)
class VegStats:
    terrain: str
    nzones: int
    tiles: int
    nanchors: int
    tiles_per_ebin: list[int]
    anch: dict[str, list[int]]
    lam: dict[str, list[float]]
    lam_tot: dict[str, float]
    g: dict[str, list[float]]
    pairN: dict[str, list[int]]
    pairD: list[int]
    anim_w: dict[str, dict[str, int]]
    mean_blk_cells: dict[str, float]
    cell: CellStats | None
    veg_blocked_frac: float
    runs: dict[str, float]


@dataclass(slots=True)
class _Acc:
    tiles_per_ebin: list[int] = field(default_factory=lambda: [0] * EBINS)
    anch: collections.defaultdict[str, list[int]] = field(
        default_factory=lambda: collections.defaultdict(lambda: [0] * EBINS)
    )
    pairN: collections.defaultdict[str, list[int]] = field(
        default_factory=lambda: collections.defaultdict(lambda: [0] * (RMAX + 1))
    )
    pairD: list[int] = field(default_factory=lambda: [0] * (RMAX + 1))
    anim_w: collections.defaultdict[str, collections.Counter[str]] = field(
        default_factory=lambda: collections.defaultdict(collections.Counter)
    )
    blocked: int = 0
    tiles: int = 0
    nzones: int = 0
    nanch: int = 0
    cells_n: int = 0
    cells_sum: int = 0
    cells_sum2: int = 0
    runs: collections.Counter[int] = field(default_factory=collections.Counter)


def _as_float(value: JsonValue) -> float:
    return float(value) if isinstance(value, int | float) else 0.0


def _int_list(value: JsonValue | None) -> list[int]:
    return [json_value.as_int(v) for v in json_value.as_list(value)]


def _float_list(value: JsonValue | None) -> list[float]:
    return [_as_float(v) for v in json_value.as_list(value)]


def _map_of[T](value: JsonValue | None, convert: Callable[[JsonValue], T]) -> dict[str, T]:
    return {k: convert(v) for k, v in json_value.as_object(value).items()}


def _stats_from_json(raw: JsonValue) -> VegStats:
    obj = json_value.as_object(raw)
    cell_obj = json_value.as_object(obj.get("cell"))
    cell = (
        CellStats(
            size=json_value.as_int(cell_obj.get("size")),
            n=json_value.as_int(cell_obj.get("n")),
            sum=json_value.as_int(cell_obj.get("sum")),
            sum2=json_value.as_int(cell_obj.get("sum2")),
        )
        if cell_obj
        else None
    )
    return VegStats(
        terrain=json_value.as_str(obj.get("terrain")),
        nzones=json_value.as_int(obj.get("nzones")),
        tiles=json_value.as_int(obj.get("tiles")),
        nanchors=json_value.as_int(obj.get("nanchors")),
        tiles_per_ebin=_int_list(obj.get("tiles_per_ebin")),
        anch=_map_of(obj.get("anch"), _int_list),
        lam=_map_of(obj.get("lam"), _float_list),
        lam_tot=_map_of(obj.get("lam_tot"), _as_float),
        g=_map_of(obj.get("g"), _float_list),
        pairN=_map_of(obj.get("pairN"), _int_list),
        pairD=_int_list(obj.get("pairD")),
        anim_w=_map_of(obj.get("anim_w"), lambda v: _map_of(v, json_value.as_int)),
        mean_blk_cells=_map_of(obj.get("mean_blk_cells"), _as_float),
        cell=cell,
        veg_blocked_frac=_as_float(obj.get("veg_blocked_frac")),
        runs=_map_of(obj.get("runs"), _as_float),
    )


def _stats_to_json(st: VegStats) -> dict[str, object]:
    return {
        "terrain": st.terrain,
        "nzones": st.nzones,
        "tiles": st.tiles,
        "nanchors": st.nanchors,
        "tiles_per_ebin": st.tiles_per_ebin,
        "anch": st.anch,
        "lam": st.lam,
        "lam_tot": st.lam_tot,
        "g": st.g,
        "pairN": st.pairN,
        "pairD": st.pairD,
        "anim_w": st.anim_w,
        "mean_blk_cells": st.mean_blk_cells,
        "cell": (
            None
            if st.cell is None
            else {"size": st.cell.size, "n": st.cell.n, "sum": st.cell.sum, "sum2": st.cell.sum2}
        ),
        "veg_blocked_frac": st.veg_blocked_frac,
        "runs": st.runs,
    }


def _footprint(catalog: Catalog, anim: str) -> Footprint:
    spec = catalog.spec(anim)
    return spec.footprint if spec is not None else Footprint.one(Role.BLOCKING)


def _anchors_of_zone(
    catalog: Catalog, fm: MapState, ts: AbstractSet[Tile]
) -> list[tuple[int, int, str, str]]:
    """[(x, y, cat_name, anim)] for DECORATION objects anchored inside the zone, excluded
    water-feature categories dropped. Category via the catalog (single source of truth)."""
    out: list[tuple[int, int, str, str]] = []
    for o in fm.objs:
        if o.level != 0 or (o.x, o.y) not in ts:
            continue
        if o.purpose != Purpose.DECORATION:
            continue
        anim = o.animation.lower().removesuffix(".def")
        cat = catalog.decor_category(anim)
        if cat is None:
            continue
        out.append((o.x, o.y, cat, anim))
    return out


def _ring_offsets(r: int) -> list[Tile]:
    """The 8r lattice offsets at Chebyshev distance exactly r (r >= 1)."""
    offs: list[Tile] = []
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            if max(abs(dx), abs(dy)) == r:
                offs.append((dx, dy))
    return offs


OFFS = {r: _ring_offsets(r) for r in range(1, RMAX + 1)}


def pair_denominator(ts: Collection[Tile]) -> list[int]:
    """D[r] = number of ORDERED in-zone tile pairs at Chebyshev distance exactly r (numpy shifts).
    This is the translation-corrected normalizer of the lattice pair-correlation estimator."""
    xs = [x for x, _ in ts]
    ys = [y for _, y in ts]
    x0, y0 = min(xs), min(ys)
    W = max(xs) - x0 + 1 + 2 * RMAX
    H = max(ys) - y0 + 1 + 2 * RMAX
    m = np.zeros((H, W), dtype=bool)
    for x, y in ts:
        m[y - y0 + RMAX, x - x0 + RMAX] = True
    D = [len(ts)]  # r=0: a tile pairs with itself
    for r in range(1, RMAX + 1):
        tot = 0
        for dx, dy in OFFS[r]:
            tot += int(np.count_nonzero(m & np.roll(np.roll(m, dy, axis=0), dx, axis=1)))
        D.append(tot)
    return D


type _Pos = collections.defaultdict[Tile, collections.Counter[str]]


def _count_stacked(a: _Acc, ca: collections.Counter[str]) -> None:
    for cat_a, n_a in ca.items():
        for cat_b, n_b in ca.items():
            n = n_a * n_b - (n_a if cat_a == cat_b else 0)
            if n > 0:
                a.pairN[f"{cat_a}|{cat_b}"][0] += n


def _count_rings(a: _Acc, pos: _Pos, p: Tile, ca: collections.Counter[str]) -> None:
    for r in range(1, RMAX + 1):
        for dx, dy in OFFS[r]:
            cb = pos.get((p[0] + dx, p[1] + dy))
            if not cb:
                continue
            for cat_a, n_a in ca.items():
                for cat_b, n_b in cb.items():
                    a.pairN[f"{cat_a}|{cat_b}"][r] += n_a * n_b


def _count_cells(a: _Acc, ts: set[Tile], pos: _Pos) -> None:
    xs = [x for x, _ in ts]
    ys2 = [y for _, y in ts]
    for cy0 in range(min(ys2), max(ys2) - CELL + 2, CELL):
        for cx0 in range(min(xs), max(xs) - CELL + 2, CELL):
            cell_tiles = [(cx0 + dx, cy0 + dy) for dy in range(CELL) for dx in range(CELL)]
            if all(t in ts for t in cell_tiles):
                n = sum(sum(pos[t].values()) for t in cell_tiles if t in pos)
                a.cells_n += 1
                a.cells_sum += n
                a.cells_sum2 += n * n


def _count_blocked(
    catalog: Catalog, a: _Acc, anchors: list[tuple[int, int, str, str]], ts: set[Tile]
) -> None:
    blocked: set[Tile] = set()
    for x, y, _c, anim in anchors:
        for cx, cy, blk in FP.anchored_cells(_footprint(catalog, anim), x, y):
            if blk and (cx, cy) in ts:
                blocked.add((cx, cy))
    a.blocked += len(blocked)
    a.runs.update(run_lengths(ts, ts - blocked))


def _accumulate_zone(catalog: Catalog, a: _Acc, fm: MapState, ts: set[Tile]) -> None:
    anchors = _anchors_of_zone(catalog, fm, ts)
    edist = edge_dist(ts)

    a.nzones += 1
    a.tiles += len(ts)
    a.nanch += len(anchors)
    for t in ts:
        a.tiles_per_ebin[min(edist[t], EBINS - 1)] += 1
    pos: _Pos = collections.defaultdict(collections.Counter)  # (x,y) -> cat counts
    for x, y, cat, anim in anchors:
        a.anch[cat][min(edist[(x, y)], EBINS - 1)] += 1
        a.anim_w[cat][anim] += 1
        pos[(x, y)][cat] += 1

    # pair counts: ordered (a,b) pairs per ring, incl. r=0 stacking
    for p, ca in pos.items():
        _count_stacked(a, ca)
        _count_rings(a, pos, p, ca)
    D = pair_denominator(ts)
    for r in range(RMAX + 1):
        a.pairD[r] += D[r]

    # coarse-cell anchor counts -> overdispersion (Fisher index) for the Cox field:
    # only cells FULLY inside the zone, so cell area is constant
    _count_cells(a, ts, pos)

    # budget target + corpus veg-only run lengths
    _count_blocked(catalog, a, anchors, ts)


def mine(catalog: Catalog, maps: Iterable[MapState]) -> dict[str, VegStats]:
    acc = {catalog.terrain_name(t): _Acc() for t in Terrain if t.is_land}
    for fm in maps:
        zones, _zl, _ = segment_level(fm.cells[0])
        for z in zones.values():
            terr = catalog.terrain_name(z.terrain_type)
            if terr not in acc or z.area < MIN_AREA:
                continue
            _accumulate_zone(catalog, acc[terr], fm, set(z.tiles_set))
    return {terr: _finalize(catalog, terr, a) for terr, a in acc.items()}


def _stats_path(terrain: str) -> Path:
    return Path(PP_DIR) / f"veg_{terrain}.json"


def save(stats: Mapping[str, VegStats]) -> None:
    for terr, st in stats.items():
        pp_cache.write(_stats_path(terr), SOURCE, _stats_to_json(st))


def _finalize(catalog: Catalog, terr: str, a: _Acc) -> VegStats:
    tot_tiles = max(a.tiles, 1)
    lam: dict[str, list[float]] = {}
    for cat, per_e in a.anch.items():
        lam[cat] = [
            (per_e[e] + 0.25) / (a.tiles_per_ebin[e] + 0.5) for e in range(EBINS)
        ]  # Laplace-smoothed
    lam_tot = {cat: sum(a.anch[cat]) / tot_tiles for cat in a.anch}
    g: dict[str, list[float]] = {}
    for key, N in a.pairN.items():
        ca, cb = key.split("|")
        la, lb = lam_tot.get(ca, 0), lam_tot.get(cb, 0)
        if la <= 0 or lb <= 0:
            continue
        g[key] = [(N[r] / a.pairD[r]) / (la * lb) if a.pairD[r] else 0.0 for r in range(RMAX + 1)]
    mean_blk = {
        cat: (
            sum(
                sum(r.blocks for _dx, _dy, r in _footprint(catalog, an).cells) * c
                for an, c in cnt.items()
            )
            / max(sum(cnt.values()), 1)
        )
        for cat, cnt in a.anim_w.items()
    }
    runs_tot = sum(a.runs.values()) or 1
    return VegStats(
        terrain=terr,
        nzones=a.nzones,
        tiles=a.tiles,
        nanchors=a.nanch,
        tiles_per_ebin=a.tiles_per_ebin,
        anch=dict(a.anch),
        lam=lam,
        lam_tot=lam_tot,
        g=g,
        pairN=dict(a.pairN),
        pairD=a.pairD,
        anim_w={c: dict(v) for c, v in a.anim_w.items()},
        mean_blk_cells=mean_blk,
        cell=CellStats(size=CELL, n=a.cells_n, sum=a.cells_sum, sum2=a.cells_sum2),
        veg_blocked_frac=a.blocked / tot_tiles,
        runs={str(k): v / runs_tot for k, v in sorted(a.runs.items())[:12]},
    )


def load(terrain: str) -> VegStats:
    return _stats_from_json(pp_cache.read(_stats_path(terrain)))


def theta(
    stats: VegStats, min_pairs: int = 30, lo: float = -1.5, hi: float = 2.0
) -> dict[str, list[float]]:
    """Pairwise log-potentials  theta[a][b][r] = clip(log ghat_ab(r))  (spec §2.6 counting fit).
    Rings with fewer than `min_pairs` observed pairs are neutral (0) — too sparse to trust."""
    th: dict[str, list[float]] = {}
    for key, gr in stats.g.items():
        N = stats.pairN[key]
        th[key] = [
            max(lo, min(hi, math.log(gr[r]))) if N[r] >= min_pairs and gr[r] > 0 else 0.0
            for r in range(RMAX + 1)
        ]
    return th


def theta_local(
    stats: VegStats,
    rint: int = 2,
    base_r: int = 4,
    min_pairs: int = 30,
    clip: tuple[float, float] = (-1.5, 1.5),
) -> dict[str, list[float]]:
    """LOCAL pair potentials, background-normalized:  theta[a][b][r] = log(g(r) / g(base_r)),
    r <= rint. The raw g(r) > 1 at ALL ranges because zones mix dense forest masses with
    clearings (large-scale inhomogeneity); fitting that as pair attraction makes the Gibbs
    process explosive. Dividing by the mid-range g isolates the genuinely LOCAL clumping /
    stacking excess; the large-scale part is carried by the Cox log-field (`cox_sigma`)."""
    lo, hi = clip
    th: dict[str, list[float]] = {}
    for key, gr in stats.g.items():
        N = stats.pairN[key]
        base = gr[base_r] if (N[base_r] >= min_pairs and gr[base_r] > 0) else None
        row: list[float] = []
        for r in range(rint + 1):
            if base and N[r] >= min_pairs and gr[r] > 0:
                row.append(max(lo, min(hi, math.log(gr[r] / base))))
            else:
                row.append(0.0)
        th[key] = row
    return th


def cox_sigma(stats: VegStats) -> float:
    """Log-field std of the Cox modulation, fitted from coarse-cell overdispersion: for a
    log-Gaussian Cox process the Fisher index of cell counts is  F = 1 + m(e^{s^2}-1)  with
    m the mean count, so  s^2 = ln(1 + (F-1)/m)  (Møller & Waagepetersen 2004, ch. 5)."""
    c = stats.cell
    if c is None or c.n < 10 or c.sum <= 0:
        return 0.0
    m = c.sum / c.n
    var = c.sum2 / c.n - m * m
    F = var / m
    return math.sqrt(max(0.0, math.log(1.0 + max(0.0, F - 1.0) / m)))


def report(terrain: str) -> tuple[VegStats, dict[str, list[float]]]:
    st = load(terrain)
    head = f"== {terrain}: zones={st.nzones} tiles={st.tiles} anchors={st.nanchors} "
    density = f"(density {st.nanchors / max(st.tiles, 1):.3f}/tile) "
    print(f"{head}{density}veg_blocked_frac={st.veg_blocked_frac:.3f}")
    lam_tot = st.lam_tot
    top = sorted(lam_tot, key=lambda name: lam_tot[name], reverse=True)[:8]
    print("  intensity by edge bin (anchors/tile):")
    for cat in top:
        row = " ".join(f"{v:.3f}" for v in st.lam[cat])
        print(f"    {cat:<18} tot={lam_tot[cat]:.4f}  by-ebin {row}")
    th = theta(st)
    print("  pair correlation g(r), r=0..6  (same-category):")
    for cat in top[:6]:
        key = f"{cat}|{cat}"
        if key in st.g:
            row = " ".join(f"{v:6.2f}" for v in st.g[key])
            print(f"    {cat:<18} {row}")
    print("  corpus veg-only open run-length fractions:", st.runs)
    return st, th


class _Args(argparse.Namespace):
    report: str = ""


def main() -> None:
    ap = argparse.ArgumentParser()
    _ = ap.add_argument("--report", metavar="TERRAIN", required=True)
    args = ap.parse_args(namespace=_Args())
    _ = report(args.report)


if __name__ == "__main__":
    main()

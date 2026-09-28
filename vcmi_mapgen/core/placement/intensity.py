"""Per-tile placement intensity over edge depth, gate distance and openness, fitted from the
corpus covariate counts."""

import collections
import math
from collections.abc import Iterable, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass

from vcmi_mapgen.core.model import (
    Tile,
)
from vcmi_mapgen.core.priors.gameplay import TerrainStats

EB, GB, OB = 6, 4, 4  # covariate bins: edge-dist, gate-dist, openness


def scaled_cap(base: int, expectation: float) -> int:
    """Area-scaled soft cap: the corpus expectation (density x area) drives the count; the
    cap only stops outliers (1.5x the expectation), never below the base floor."""
    return max(base, math.ceil(expectation * 1.5))


def gate_bin(d: int) -> int:
    return min(d // 3, GB - 1)


def open_bin(n_open_5x5: int) -> int:
    return min(n_open_5x5 // 7, OB - 1)


def gate_dist(ts: AbstractSet[Tile], gates: Iterable[Tile]) -> dict[Tile, int]:
    """4-connected BFS steps from the zone's rim gates (corpus + generated zones alike)."""
    d = {g: 0 for g in gates if g in ts}
    q = collections.deque(d)
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if n in ts and n not in d:
                d[n] = d[(x, y)] + 1
                q.append(n)
    return d


def openness(open_set: AbstractSet[Tile]) -> dict[Tile, int]:
    """Per open tile: number of open tiles in its 5x5 window (low = nook/chokepoint)."""
    out: dict[Tile, int] = {}
    for x, y in open_set:
        out[(x, y)] = sum(
            1 for dx in range(-2, 3) for dy in range(-2, 3) if (x + dx, y + dy) in open_set
        )
    return out


@dataclass(frozen=True, slots=True)
class Covariates:
    ed: Mapping[Tile, int]
    gd: Mapping[Tile, int]
    op: Mapping[Tile, int] | None = None


def theta_covariates(st_t: TerrainStats, purpose: str) -> dict[str, list[float]]:
    """The L3 counting fit: th[bin] = log of the purpose's relative intensity in that covariate
    bin vs its zone-wide average (Laplace-smoothed, clipped to ±2). Additive across covariates
    — the log-linear model of spec §7.1 with independent covariate effects."""
    out: dict[str, list[float]] = {}
    tot = sum(st_t.counts.get(p, 0) for p in [purpose]) or 1
    base = tot / max(st_t.tiles, 1)
    for key, cov, tile_bins, nbins in (
        ("e", st_t.e, st_t.tiles_e, EB),
        ("g", st_t.g, st_t.tiles_g, GB),
        ("o", st_t.o, st_t.tiles_o, OB),
    ):
        cnts = cov.get(purpose, [0] * nbins)
        th: list[float] = []
        for b in range(nbins):
            lam_b = (cnts[b] + 0.5) / (tile_bins[b] + 0.5 / max(base, 1e-9))
            th.append(max(-2.0, min(2.0, math.log(lam_b / base))))
        out[key] = th
    return out


def intensity_weights(
    ts: Iterable[Tile], purpose: str, st_t: TerrainStats, cov: Covariates
) -> dict[Tile, float]:
    """Per-tile placement intensity  w(u) = exp(th_e + th_g (+ th_o))  from the L3 fit."""
    th = theta_covariates(st_t, purpose)
    ed, gd, op = cov.ed, cov.gd, cov.op
    w: dict[Tile, float] = {}
    for t in sorted(ts):
        s = th["e"][min(ed[t], EB - 1)] + th["g"][gate_bin(gd.get(t, 12))]
        if op is not None:
            s += th["o"][open_bin(op[t])] if t in op else -2.0
        w[t] = math.exp(s)
    return w

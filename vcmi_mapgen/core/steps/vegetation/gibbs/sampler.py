"""Marked-point-process vegetation sampler (spec §2.7 + M1/M2).

Samples a zone's decoration configuration from the Gibbs marked point process fitted by
`pp_stats` — birth/death Metropolis-Hastings on OBJECT configurations, not tiles:

  - marks = catalog decoration identities (`Catalog.decor`), weighted by corpus frequency
    (a spatial statistic; identity/mask/category always resolve through the catalog),
  - Papangelou conditional intensity
        lam*(u,c) = exp(alpha) * lam[c][ebin(u)] * M(u) * exp(E(u,c))
    where the pattern's two scales are split (a purely attractive pairwise Gibbs process is
    EXPLOSIVE — raw log g > 0 at all ranges compounds into one runaway clump):
      * M(u) — LOG-GAUSSIAN COX modulation: a smooth seeded value-noise log-field carrying the
        LARGE-SCALE density variation (forest masses vs clearings). Its std sigma is FITTED from
        corpus coarse-cell overdispersion (`pp_stats.cox_sigma`, Fisher-index inversion).
      * E(u,c) — LOCAL interaction only (rings r <= RINT), background-normalized potentials
        theta = log(g(r)/g(4)) (`pp_stats.theta_local`), GEYER-SATURATED: each (category, ring)
        neighbour count is capped at SAT so lam* stays bounded (Geyer 1999).
  - NO vegetation hard core — footprints may overlap/stack (corpus-legal); stacking is priced
    by the learned r=0 potential, and a birth whose blocking cells all sit under STACK_CAP
    objects already is refused, so the coverage offset cannot pile hidden sprites,
  - hard zeros only where the game needs them: a blocking cell off-zone or on the PROTECTED
    walkable web (spanning backbone + gates, kept constructive per spec §5). A blocking cell
    past the map edge is legal, as in the corpus, and counts toward nothing,
  - budget: the realized blocking-union coverage is steered to the corpus `veg_blocked_frac`
    by a global log-offset alpha, corrected on a Boolean-model (coverage-exponent) schedule.

The blocked mask is EMERGENT (union of sampled footprints) — run-length stats become the
validation metric, per the M1 experiment:

    uv run python -m vcmi_mapgen.cli.veg_experiment --map "All for One" --zone 11
"""

import math
import random
from typing import cast, final

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.grid.noise import value_noise
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.planning.web import ZoneRef
from vcmi_mapgen.core.steps.vegetation.canvas import ZoneCanvas, zone_rng
from vcmi_mapgen.core.steps.vegetation.mix import ZoneMix
from vcmi_mapgen.core.steps.vegetation.model import RINT, VegModel
from vcmi_mapgen.core.steps.vegetation.sampler import SampleOptions, ZoneGrowth

KW = 2 * RINT + 1  # interaction window (5x5)
STEPS_PER_TILE = 40  # MH proposals per zone tile
SAT = 2  # Geyer saturation: neighbour count cap per (category, ring)
COX_CELL = 7  # value-noise cell of the Cox log-field (~ the corpus CELL scale)
STACK_CAP = 2


def _f(a: NDArray[np.float64], *idx: int) -> float:
    return cast(float, a[idx])


def _i(a: NDArray[np.int8], *idx: int) -> int:
    return cast(int, a[idx])


BORDER_W = 2.5  # log-intensity bonus on `border` tiles (zone-front belt):
#                                 e^2.5 ~ 12x Papangelou intensity, so growth concentrates
#                                 along zone borders and reads as a natural ridge. Each side
#                                 only reaches ~70-90% front coverage (Geyer saturation), but
#                                 BOTH zones densify their own side and a crossing needs an
#                                 aligned open pair — measured on the 2-zone probe, every
#                                 surviving crossing is the planned entrance band. The global
#                                 coverage correction (alpha -> corpus veg_blocked_frac) keeps
#                                 TOTAL vegetation corpus-like, so this REDISTRIBUTES mass to
#                                 the border rather than inflating overall density.


@final
class GibbsSampler:
    def sample(self, zone: ZoneRef, model: VegModel, seed: int, opts: SampleOptions) -> ZoneGrowth:
        """Birth/death MH over decoration configurations in one zone. Returns
        (objects, blocked_set, prot) with objects = list[PlacedObject] on the zone's level.
        `forbid` tiles (gameplay footprints + approach tiles) admit NO vegetation at all —
        neither an anchor nor any footprint cell (decor must not bury gameplay, per the repo
        rule). `border` tiles carry a +BORDER_W log-intensity bonus — the zone-isolation
        lever: the zone's contact front (minus its planned entrance bands, which sit in `prot`
        as hard zeros) densifies into a vegetation ridge with corpus-correct species/clumping,
        leaving only the planned entrances open.
        `impassable` tiles (gameplay footprints) count as walls for connectivity. The canvas
        refuses a birth or a death that would cut open ground off from the protected web, so
        no walled-off open ground ever forms."""
        if not model.cats:
            return [], set(), set()
        return _GibbsRun(ZoneCanvas(zone, model, opts), model, zone_rng(zone, seed)).run()


def _ring_masks() -> NDArray[np.float64]:
    RM: NDArray[np.float64] = np.zeros((RINT + 1, KW, KW))
    for dy in range(-RINT, RINT + 1):
        for dx in range(-RINT, RINT + 1):
            RM[max(abs(dx), abs(dy)), dy + RINT, dx + RINT] = 1.0
    return RM


@final
class _GibbsRun:
    def __init__(self, canvas: ZoneCanvas, model: VegModel, rng: random.Random) -> None:
        self.canvas: ZoneCanvas = canvas
        self.rng: random.Random = rng
        self.mix: ZoneMix = ZoneMix(model, canvas.tiles_per_ebin, rng)
        self.A: int = len(model.cats)
        self.L: NDArray[np.float64] = model.L
        self.T: NDArray[np.float64] = model.T
        self.RM = _ring_masks()
        self.cox = self._cox_field(model.sigma)
        self.att: NDArray[np.float64] = np.where(canvas.border, BORDER_W, 0.0)
        self.C = np.zeros((self.A, canvas.H + 2 * RINT, canvas.W + 2 * RINT), dtype=np.int16)
        self.ncat = np.zeros(self.A, dtype=np.int64)
        self.alpha = 0.0
        self.alpha_c: NDArray[np.float64] = np.zeros(self.A)
        self.target = model.target

    def _cox_field(self, sigma: float) -> NDArray[np.float64]:
        # log-Gaussian Cox modulation: smooth value noise, standardized over the zone, then
        # M = exp(sigma*G - sigma^2/2)  (mean-one lognormal -> carries forest-mass/clearing scale)
        cv = self.canvas
        cox: NDArray[np.float64] = np.ones((cv.H, cv.W))
        if sigma > 0:
            noise = value_noise(cv.W, cv.H, COX_CELL, self.rng)
            field: NDArray[np.float64] = np.array(noise)
            v: NDArray[np.float64] = field[cv.inz]
            field = cast(NDArray[np.float64], (field - v.mean()) / max(cast(float, v.std()), 1e-6))
            cox = np.exp(sigma * field - 0.5 * sigma * sigma)
        return cox

    def energy(self, c: int, x: int, y: int, self_present: bool = False) -> float:
        """Geyer-saturated local interaction  sum_co,r theta[c][co][r] * min(n_co(r), SAT)."""
        cv = self.canvas
        ly, lx = y - cv.y0, x - cv.x0  # padded window: [ly, ly+KW) x [lx, lx+KW)
        win = self.C[:, ly : ly + KW, lx : lx + KW]
        rc: NDArray[np.float64] = np.tensordot(
            win, self.RM, axes=([1, 2], [1, 2])
        )  # (A cats, RINT+1 rings) neighbour counts
        if self_present:
            rc[c, 0] -= 1  # death eval: exclude the object itself
        weighted = cast(NDArray[np.float64], self.T[c] * np.minimum(rc, SAT))
        return cast(float, weighted.sum())

    def run(self) -> ZoneGrowth:
        rng = self.rng
        total = STEPS_PER_TILE * self.canvas.Nt
        cat_correct_at = {int(total * f) for f in (0.2, 0.35, 0.5)}
        cov_correct_at = {int(total * f) for f in (0.65, 0.8)}
        for step in range(total):
            self._correct(step, cat_correct_at, cov_correct_at)
            if rng.random() < 0.5:  # ---- birth
                self._birth()
            else:  # ---- death
                self._death()
        return self.canvas.result()

    def _correct(self, step: int, cat_correct_at: set[int], cov_correct_at: set[int]) -> None:
        nblocked, Nt = self.canvas.nblocked, self.canvas.Nt
        if step in cat_correct_at:  # per-category intercepts -> corpus counts
            self.alpha_c += np.clip(
                np.log(np.maximum(self.mix.nexp, 1e-3) / np.maximum(self.ncat, 0.5)), -0.9, 0.9
            )
        if step in cov_correct_at and nblocked > 0:  # Boolean coverage-exponent correction
            f_cur = nblocked / Nt
            c_cur = -math.log(max(1e-6, 1.0 - min(f_cur, 0.999)))
            c_tgt = -math.log(max(1e-6, 1.0 - min(self.target, 0.999)))
            self.alpha += max(-0.9, min(0.9, math.log(c_tgt / max(c_cur, 1e-6))))

    def _lam_star(self, c: int, x: int, y: int, self_present: bool) -> float:
        ly, lx = y - self.canvas.y0, x - self.canvas.x0
        return (
            math.exp(
                self.alpha
                + _f(self.alpha_c, c)
                + _f(self.att, ly, lx)
                + self.energy(c, x, y, self_present=self_present)
            )
            * _f(self.L, c, _i(self.canvas.eb, ly, lx))
            * _f(self.cox, ly, lx)
        )

    def _birth(self) -> None:
        rng, cv = self.rng, self.canvas
        x, y = cv.tiles[rng.randrange(cv.Nt)]
        if (x, y) in cv.forbid:
            return
        c = self.mix.draw_category()
        ii = self.mix.draw_identity(c)
        cells = cv.blocked_cells(c, ii, x, y)
        if cells is None or self._buried(cells):
            return
        lam_star = self._lam_star(c, x, y, False)
        acc = lam_star * cv.Nt / ((len(cv.objs) + 1) * _f(self.mix.qc, c))
        if rng.random() < acc and cv.try_place((x, y, c, ii), cells):
            self._count(c, x, y, 1)

    def _buried(self, cells: list[Tile]) -> bool:
        x0, y0, blkcnt = self.canvas.x0, self.canvas.y0, self.canvas.blkcnt
        return all(blkcnt[by - y0, bx - x0] >= STACK_CAP for bx, by in cells)

    def _count(self, c: int, x: int, y: int, d: int) -> None:
        self.ncat[c] += d
        self.C[c, y - self.canvas.y0 + RINT, x - self.canvas.x0 + RINT] += d

    def _death(self) -> None:
        rng, cv = self.rng, self.canvas
        n = len(cv.objs)
        if n == 0:
            return
        j = rng.randrange(n)
        x, y, c, _ii = cv.objs[j]
        lam_star = self._lam_star(c, x, y, True)
        acc = (n * _f(self.mix.qc, c)) / max(lam_star * cv.Nt, 1e-300)
        if rng.random() < acc and cv.try_remove(j):
            self._count(c, x, y, -1)

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
    walkable web (spanning backbone + gates, kept constructive per spec §5),
  - budget: the realized blocking-union coverage is steered to the corpus `veg_blocked_frac`
    by a global log-offset alpha, corrected on a Boolean-model (coverage-exponent) schedule.

The blocked mask is EMERGENT (union of sampled footprints) — run-length stats become the
validation metric, per the M1 experiment:

    uv run python -m vcmi_mapgen.veg_experiment --map "All for One" --zone 11
"""

import collections
import math
import random
from collections.abc import Collection, Iterable, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import cast, final

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.geometry import EBINS, edge_dist
from vcmi_mapgen.core.grid.noise import value_noise
from vcmi_mapgen.core.grid.paths import SPACING, farthest_points, geodesic_path
from vcmi_mapgen.core.model import Identity, PlacedObject, Tile, Zone
from vcmi_mapgen.core.steps.vegetation import stats as PS
from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.kit.topology import zone_fronts, zone_gate_bands

RINT = 2  # local-interaction range (Chebyshev rings 0..RINT)
KW = 2 * RINT + 1  # interaction window (5x5)
STEPS_PER_TILE = 40  # MH proposals per zone tile
SAT = 2  # Geyer saturation: neighbour count cap per (category, ring)
COX_CELL = 7  # value-noise cell of the Cox log-field (~ the corpus CELL scale)
STACK_CAP = 2
BASE_W = 0.3  # base weight so native-but-corpus-rare sprites stay possible


_NO_TILES: frozenset[Tile] = frozenset()


def _f(a: NDArray[np.float64], *idx: int) -> float:
    return cast(float, a[idx])


def _i(a: NDArray[np.int8], *idx: int) -> int:
    return cast(int, a[idx])


@dataclass(slots=True)
class VegModel:
    terrain: str
    cats: list[str]
    L: NDArray[np.float64]
    T: NDArray[np.float64]
    idents: list[list[Identity]]
    iweights: list[list[float]]
    iblk: list[list[list[Tile]]]
    ifoot: list[list[list[Tile]]]
    sigma: float
    target: float
    runs: dict[str, float]


def build_model(catalog: Catalog, terrain: str) -> VegModel:
    """Fitted per-terrain sampling model: category list, intensities, theta kernel, ident pools."""
    st = PS.load(terrain)
    th = PS.theta_local(st, rint=RINT)

    by_cat: collections.defaultdict[str, list[Identity]] = collections.defaultdict(list)
    for ident in catalog.decor(terrain):
        cat = catalog.decor_category(ident.animation)
        if cat is not None:
            by_cat[cat].append(ident)

    cats = [
        c
        for c in sorted(st.lam_tot, key=lambda name: st.lam_tot[name], reverse=True)
        if st.lam_tot[c] > 0 and by_cat.get(c)
    ]
    A = len(cats)
    cidx = {c: i for i, c in enumerate(cats)}

    L = np.zeros((A, EBINS))
    for c in cats:
        L[cidx[c]] = st.lam[c]

    T = np.zeros((A, A, RINT + 1))
    for key, row in th.items():
        ca, cb = key.split("|")
        if ca in cidx and cb in cidx:
            T[cidx[ca], cidx[cb]] = row

    idents: list[list[Identity]] = []
    iweights: list[list[float]] = []
    iblk: list[list[list[Tile]]] = []
    ifoot: list[list[list[Tile]]] = []
    for c in cats:
        w = st.anim_w.get(c, {})
        ids = by_cat[c]
        idents.append(ids)
        iweights.append([w.get(i.animation.lower(), 0) + BASE_W for i in ids])
        blk: list[list[Tile]] = []
        foot: list[list[Tile]] = []
        for i in ids:
            cells = [(cx, cy, b) for cx, cy, b in OR.mask_cells(i.mask, 0, 0)]
            blk.append([(cx, cy) for cx, cy, b in cells if b])
            foot.append([(cx, cy) for cx, cy, _b in cells])
        iblk.append(blk)
        ifoot.append(foot)

    return VegModel(
        terrain=terrain,
        cats=cats,
        L=L,
        T=T,
        idents=idents,
        iweights=iweights,
        iblk=iblk,
        ifoot=ifoot,
        sigma=PS.cox_sigma(st),
        target=st.veg_blocked_frac,
        runs=st.runs,
    )


def _band_component(rep: Tile, band: AbstractSet[Tile]) -> set[Tile]:
    """The 4-connected part of `band` containing `rep`. A diagonal-only band tile would be
    a protected fragment that no walkable path reaches."""
    if rep not in band:
        return set()
    comp = {rep}
    stack = [rep]
    while stack:
        x, y = stack.pop()
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n in band and n not in comp:
                comp.add(n)
                stack.append(n)
    return comp


@dataclass(frozen=True, slots=True)
class ZoneRef:
    ts: AbstractSet[Tile]
    zones: Mapping[int, Zone]
    zid: int


@dataclass(frozen=True, slots=True)
class WebOptions:
    spacing: int = SPACING
    extra_nodes: Iterable[Tile] = ()
    avoid: Collection[Tile] = _NO_TILES
    open_frac: float = 0.5
    entrances: Iterable[tuple[Tile, frozenset[Tile], int]] | None = None
    keep_off: Collection[Tile] = _NO_TILES


_DEFAULT_WEB = WebOptions()


def protected_web(
    zone: ZoneRef,
    edist: Mapping[Tile, int],
    seedt: Tile,
    opts: WebOptions = _DEFAULT_WEB,
) -> set[Tile]:
    """The PROTECTED walkable set: spanning backbone over farthest-point nodes + rim gate
    BANDS (constructive global connectivity, reusing kit.topology's helpers — spec §5).

    Gates are corpus-wide bands of the zone-contact front (`open_frac` = the mined fraction
    of corpus zone-border tiles left passable): the whole band is protected, so vegetation
    can never wall a border down to a 1-tile corridor — generated borders stay as open as
    real corpus borders. `extra_nodes` are mandatory destinations (gameplay approach tiles —
    every placed object stays reachable); `avoid` tiles (gameplay footprints) are
    impassable, so corridors route AROUND towns/mines instead of through them.

    `entrances` (this zone's `kit.topology.plan_entrances` entries) switches the border model
    from corpus-open to ISOLATED: only the planned narrow entrance bands are protected —
    the rest of the front is left plantable, and `sample_zone`'s border bias actively
    densifies it (the map-level isolation redesign). `keep_off` (the caller's 8-connected
    rim: every tile with an 8-neighbour in another zone) further restricts backbone
    ROUTING in that mode — a web corridor pinned to the rim would both hold the ridge open
    and be unsealable by `pp_map.seal_zone_borders`."""
    ts, zones, zid = zone.ts, zone.zones, zone.zid
    avoid, keep_off, entrances = opts.avoid, opts.keep_off, opts.entrances
    ts_free = ts - set(avoid)
    if seedt not in ts_free:
        seedt = min(ts_free, key=lambda t: (t[0] - seedt[0]) ** 2 + (t[1] - seedt[1]) ** 2)
    gate_bands: list[tuple[Tile, frozenset[Tile]]]
    if entrances is not None:
        gate_bands = [(rep, band) for rep, band, _other in entrances]
        # keep the backbone OFF the non-entrance front/rim: a path hugging the border would
        # hold a protected walkable lane exactly where the border bias is trying to grow
        # the isolation ridge. Entrance bands stay in the routing domain (a rep is reached
        # through its own band); fall back to the full zone if a node is only reachable
        # along the front.
        fronts = zone_fronts(ts, zones, zid)
        front = {t for tiles in fronts.values() for t in tiles}
        band_all = {t for _r, b in gate_bands for t in b}
        path_ts = ts_free - ((front | set(keep_off)) - band_all)
    else:
        gate_bands = zone_gate_bands(ts, zones, zid, open_frac=opts.open_frac)
        path_ts = ts_free
    gates = [r for r, _b in gate_bands]
    interior = [t for t in ts_free if edist.get(t, 0) >= 2] or list(ts_free)
    nodes = farthest_points(ts_free, seedt, opts.spacing, cand=interior)
    for g in list(gates) + [n for n in opts.extra_nodes if n in ts_free]:
        if g in ts_free and g not in nodes:
            nodes.append(g)
    prot = {seedt}
    connected = [seedt]
    remaining = [n for n in nodes if n != seedt]
    while remaining:
        best_r: Tile = remaining[0]
        best_c: Tile = connected[0]
        bd = 1 << 60
        for r in remaining:
            for c in connected:
                d = (r[0] - c[0]) ** 2 + (r[1] - c[1]) ** 2
                if d < bd:
                    bd, best_r, best_c = d, r, c
        path = (
            geodesic_path(best_c, best_r, path_ts)
            or geodesic_path(best_c, best_r, ts_free)
            or geodesic_path(best_c, best_r, ts)
        )
        prot.update(path)
        connected.append(best_r)
        remaining.remove(best_r)
    for rep, band in gate_bands:
        prot.update(_band_component(rep, band & ts_free))
    return prot - set(avoid)


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


@dataclass(frozen=True, slots=True)
class SampleOptions:
    steps_per_tile: int = STEPS_PER_TILE
    prot: AbstractSet[Tile] | None = None
    forbid: AbstractSet[Tile] = _NO_TILES
    border: Collection[Tile] = _NO_TILES
    impassable: AbstractSet[Tile] = _NO_TILES


_DEFAULT_SAMPLE = SampleOptions()


def sample_zone(
    zone: ZoneRef,
    model: VegModel,
    seed: int = 1,
    opts: SampleOptions = _DEFAULT_SAMPLE,
) -> tuple[list[PlacedObject], set[Tile], AbstractSet[Tile]]:
    """Birth/death MH over decoration configurations in one zone. Returns
    (objects, blocked_set, prot) with objects = list[PlacedObject] on level 0.
    `forbid` tiles (gameplay footprints + approach tiles) admit NO vegetation at all —
    neither an anchor nor any footprint cell (decor must not bury gameplay, per the repo rule).
    `border` tiles carry a +BORDER_W log-intensity bonus — the zone-isolation lever: the
    zone's contact front (minus its planned entrance bands, which sit in `prot` as hard
    zeros) densifies into a vegetation ridge with corpus-correct species/clumping, leaving
    only the planned entrances open.
    `impassable` tiles (gameplay footprints) count as walls for connectivity. A birth is
    refused when its blocking cells would cut any open 4-neighbour off from the protected
    web, so no walled-off open ground ever forms."""
    A = len(model.cats)
    if A == 0:
        return [], set(), set()
    rng = random.Random(seed ^ (zone.zid * 2654435761 & 0xFFFFFFFF))
    return _ZoneSampler(zone, model, rng, opts).run()


def _ring_masks() -> NDArray[np.float64]:
    RM: NDArray[np.float64] = np.zeros((RINT + 1, KW, KW))
    for dy in range(-RINT, RINT + 1):
        for dx in range(-RINT, RINT + 1):
            RM[max(abs(dx), abs(dy)), dy + RINT, dx + RINT] = 1.0
    return RM


@final
class _ZoneSampler:
    def __init__(
        self, zone: ZoneRef, model: VegModel, rng: random.Random, opts: SampleOptions
    ) -> None:
        ts = zone.ts
        self.model = model
        self.rng = rng
        self.forbid = opts.forbid
        self.steps_per_tile = opts.steps_per_tile
        A = len(model.cats)
        self.A = A

        xs = [x for x, _ in ts]
        ys = [y for _, y in ts]
        self.x0, self.y0 = min(xs), min(ys)
        self.W = max(xs) - self.x0 + 1
        self.H = max(ys) - self.y0 + 1
        self.inz = self._zone_mask(ts)
        edist = edge_dist(ts)
        self.eb = self._edge_bins(ts, edist)

        cx, cy = zone.zones[zone.zid].centroid
        seedt = min(ts, key=lambda t: (t[0] - round(cx)) ** 2 + (t[1] - round(cy)) ** 2)
        prot = opts.prot
        if prot is None:
            prot = protected_web(zone, edist, seedt)
        self.prot: AbstractSet[Tile] = prot
        self.protm = self._prot_mask(prot)
        self.solid = self._solid_mask(opts.impassable)

        self.L: NDArray[np.float64] = model.L
        self.T: NDArray[np.float64] = model.T
        self.tiles = sorted(ts)
        self.Nt = len(self.tiles)
        # birth proposal: category mix from the zone's total first-order mass; `nexp` is also the
        # corpus-expected object count per category for this zone (the intercept-correction target)
        ebin_tiles = np.bincount(self.eb[self.inz].ravel(), minlength=EBINS)
        self.nexp = cast(NDArray[np.float64], (self.L * ebin_tiles[None, :]).sum(axis=1))
        self.qc = cast(NDArray[np.float64], self.nexp / self.nexp.sum())
        self.qc_cum: NDArray[np.float64] = np.cumsum(self.qc)

        # ring masks over the interaction window: RM[r] selects the Chebyshev ring r
        self.RM = _ring_masks()

        self.cox = self._cox_field(model.sigma)
        self.att = self._bonus_grid(opts.border)

        # padded per-category anchor-count grid (padding = no bounds checks on the window)
        self.C = np.zeros((A, self.H + 2 * RINT, self.W + 2 * RINT), dtype=np.int16)
        self.blkcnt = np.zeros((self.H, self.W), dtype=np.int32)  # blocking multiplicity per tile
        self.objs: list[tuple[int, int, int, int]] = []  # (x, y, cat, ident_idx)
        self.ncat = np.zeros(A, dtype=np.int64)  # objects per category (correction target)
        self.nblocked = 0
        self.alpha = 0.0  # global coverage offset
        self.alpha_c: NDArray[np.float64] = np.zeros(A)  # per-category intercept corrections
        self.target = model.target

    def _zone_mask(self, ts: AbstractSet[Tile]) -> NDArray[np.bool_]:
        inz: NDArray[np.bool_] = np.zeros((self.H, self.W), dtype=bool)
        for x, y in ts:
            inz[y - self.y0, x - self.x0] = True
        return inz

    def _edge_bins(self, ts: AbstractSet[Tile], edist: Mapping[Tile, int]) -> NDArray[np.int8]:
        eb: NDArray[np.int8] = np.zeros((self.H, self.W), dtype=np.int8)
        for x, y in ts:
            eb[y - self.y0, x - self.x0] = min(edist[(x, y)], EBINS - 1)
        return eb

    def _prot_mask(self, prot: AbstractSet[Tile]) -> NDArray[np.bool_]:
        protm: NDArray[np.bool_] = np.zeros((self.H, self.W), dtype=np.bool_)
        for x, y in prot:
            protm[y - self.y0, x - self.x0] = True
        return protm

    def _solid_mask(self, impassable: AbstractSet[Tile]) -> NDArray[np.bool_]:
        x0, y0, W, H = self.x0, self.y0, self.W, self.H
        solid: NDArray[np.bool_] = np.logical_not(self.inz)
        for x, y in impassable:
            if 0 <= x - x0 < W and 0 <= y - y0 < H:
                solid[y - y0, x - x0] = True
        return solid

    def _cox_field(self, sigma: float) -> NDArray[np.float64]:
        # log-Gaussian Cox modulation: smooth value noise, standardized over the zone, then
        # M = exp(sigma*G - sigma^2/2)  (mean-one lognormal -> carries forest-mass/clearing scale)
        cox: NDArray[np.float64] = np.ones((self.H, self.W))
        if sigma > 0:
            noise = value_noise(self.W, self.H, COX_CELL, self.rng)
            field: NDArray[np.float64] = np.array(noise)
            v: NDArray[np.float64] = field[self.inz]
            field = cast(NDArray[np.float64], (field - v.mean()) / max(cast(float, v.std()), 1e-6))
            cox = np.exp(sigma * field - 0.5 * sigma * sigma)
        return cox

    def _bonus_grid(self, border: Collection[Tile]) -> NDArray[np.float64]:
        x0, y0, W, H = self.x0, self.y0, self.W, self.H
        att: NDArray[np.float64] = np.zeros((H, W))  # additive log-bonus grid
        for x, y in border:  # zone-front densification
            if 0 <= x - x0 < W and 0 <= y - y0 < H:
                att[y - y0, x - x0] += BORDER_W
        return att

    def energy(self, c: int, x: int, y: int, self_present: bool = False) -> float:
        """Geyer-saturated local interaction  sum_co,r theta[c][co][r] * min(n_co(r), SAT)."""
        ly, lx = y - self.y0, x - self.x0  # padded window: [ly, ly+KW) x [lx, lx+KW)
        win = self.C[:, ly : ly + KW, lx : lx + KW]
        rc: NDArray[np.float64] = np.tensordot(
            win, self.RM, axes=([1, 2], [1, 2])
        )  # (A cats, RINT+1 rings) neighbour counts
        if self_present:
            rc[c, 0] -= 1  # death eval: exclude the object itself
        weighted = cast(NDArray[np.float64], self.T[c] * np.minimum(rc, SAT))
        return cast(float, weighted.sum())

    def blocked_cells(self, c: int, ii: int, x: int, y: int) -> list[Tile] | None:
        """Absolute blocking cells of ident ii of category c anchored at (x,y); None = illegal."""
        x0, y0, W, H = self.x0, self.y0, self.W, self.H
        inz, protm, forbid, model = self.inz, self.protm, self.forbid, self.model
        cells: list[Tile] = []
        for dx, dy in model.iblk[c][ii]:
            bx, by = x + dx, y + dy
            lx, ly = bx - x0, by - y0
            if (
                not (0 <= lx < W and 0 <= ly < H)
                or not inz[ly, lx]
                or protm[ly, lx]
                or (bx, by) in forbid
            ):
                return None
            cells.append((bx, by))
        if any((x + dx, y + dy) in forbid for dx, dy in model.ifoot[c][ii]):
            return None
        return cells

    def frees_connected(self, cells: list[Tile]) -> bool:
        """Whether every tile freed by removing `cells` reaches the protected web through open
        tiles or other freed tiles."""
        x0, y0, W, H = self.x0, self.y0, self.W, self.H
        solid, protm, blkcnt = self.solid, self.protm, self.blkcnt
        freed = {
            (bx, by)
            for bx, by in cells
            if blkcnt[by - y0, bx - x0] == 1 and not solid[by - y0, bx - x0]
        }
        linked: set[Tile] = set()
        for start in freed:
            if start in linked:
                continue
            seen = {start}
            queue = collections.deque([start])
            found = bool(cast(np.bool_, protm[start[1] - y0, start[0] - x0]))
            while queue and not found:
                ux, uy = queue.popleft()
                for m in ((ux + 1, uy), (ux - 1, uy), (ux, uy + 1), (ux, uy - 1)):
                    mlx, mly = m[0] - x0, m[1] - y0
                    if (
                        m in seen
                        or not (0 <= mlx < W and 0 <= mly < H)
                        or solid[mly, mlx]
                        or (blkcnt[mly, mlx] > 0 and m not in freed)
                    ):
                        continue
                    if protm[mly, mlx] or m in linked:
                        found = True
                        break
                    seen.add(m)
                    queue.append(m)
            if not found:
                return False
            linked |= seen
        return True

    def keeps_connected(self, cells: list[Tile]) -> bool:
        """Whether every open 4-neighbour of `cells` still reaches the protected web once
        `cells` are blocked."""
        x0, y0, W, H = self.x0, self.y0, self.W, self.H
        solid, blkcnt = self.solid, self.blkcnt
        walls = set(cells)
        linked: set[Tile] = set()
        for bx, by in cells:
            for nx, ny in ((bx + 1, by), (bx - 1, by), (bx, by + 1), (bx, by - 1)):
                n = (nx, ny)
                lx, ly = nx - x0, ny - y0
                if (
                    n in walls
                    or n in linked
                    or not (0 <= lx < W and 0 <= ly < H)
                    or solid[ly, lx]
                    or blkcnt[ly, lx] > 0
                ):
                    continue
                seen = self._reach_web(n, walls, linked)
                if seen is None:
                    return False
                linked |= seen
        return True

    def _reach_web(
        self, n: Tile, walls: AbstractSet[Tile], linked: AbstractSet[Tile]
    ) -> set[Tile] | None:
        x0, y0, W, H = self.x0, self.y0, self.W, self.H
        solid, protm, blkcnt = self.solid, self.protm, self.blkcnt
        seen = {n}
        queue = collections.deque([n])
        found = bool(cast(np.bool_, protm[n[1] - y0, n[0] - x0]))
        while queue and not found:
            cx_, cy_ = queue.popleft()
            for mx, my in ((cx_ + 1, cy_), (cx_ - 1, cy_), (cx_, cy_ + 1), (cx_, cy_ - 1)):
                m = (mx, my)
                mlx, mly = mx - x0, my - y0
                if (
                    m in seen
                    or m in walls
                    or not (0 <= mlx < W and 0 <= mly < H)
                    or solid[mly, mlx]
                    or blkcnt[mly, mlx] > 0
                ):
                    continue
                if protm[mly, mlx] or m in linked:
                    found = True
                    break
                seen.add(m)
                queue.append(m)
        if not found:
            return None
        return seen

    def run(self) -> tuple[list[PlacedObject], set[Tile], AbstractSet[Tile]]:
        rng = self.rng
        total = self.steps_per_tile * self.Nt
        cat_correct_at = {int(total * f) for f in (0.2, 0.35, 0.5)}
        cov_correct_at = {int(total * f) for f in (0.65, 0.8)}
        for step in range(total):
            self._correct(step, cat_correct_at, cov_correct_at)
            if rng.random() < 0.5:  # ---- birth
                self._birth()
            else:  # ---- death
                self._death()
        return self._result()

    def _correct(self, step: int, cat_correct_at: set[int], cov_correct_at: set[int]) -> None:
        if step in cat_correct_at:  # per-category intercepts -> corpus counts
            self.alpha_c += np.clip(
                np.log(np.maximum(self.nexp, 1e-3) / np.maximum(self.ncat, 0.5)), -0.9, 0.9
            )
        if step in cov_correct_at and self.nblocked > 0:  # Boolean coverage-exponent correction
            f_cur = self.nblocked / self.Nt
            c_cur = -math.log(max(1e-6, 1.0 - min(f_cur, 0.999)))
            c_tgt = -math.log(max(1e-6, 1.0 - min(self.target, 0.999)))
            self.alpha += max(-0.9, min(0.9, math.log(c_tgt / max(c_cur, 1e-6))))

    def _lam_star(self, c: int, x: int, y: int, self_present: bool) -> float:
        ly, lx = y - self.y0, x - self.x0
        return (
            math.exp(
                self.alpha
                + _f(self.alpha_c, c)
                + _f(self.att, ly, lx)
                + self.energy(c, x, y, self_present=self_present)
            )
            * _f(self.L, c, _i(self.eb, ly, lx))
            * _f(self.cox, ly, lx)
        )

    def _birth(self) -> None:
        rng = self.rng
        x, y = self.tiles[rng.randrange(self.Nt)]
        if (x, y) in self.forbid:
            return
        r = rng.random()
        c = min(int(np.searchsorted(self.qc_cum, r)), self.A - 1)
        ws = self.model.iweights[c]
        ii = rng.choices(range(len(ws)), weights=ws, k=1)[0]
        cells = self.blocked_cells(c, ii, x, y)
        if cells is None or self._buried(cells):
            return
        lam_star = self._lam_star(c, x, y, False)
        acc = lam_star * self.Nt / ((len(self.objs) + 1) * _f(self.qc, c))
        if rng.random() < acc and self.keeps_connected(cells):
            self._add((x, y, c, ii), cells)

    def _buried(self, cells: list[Tile]) -> bool:
        x0, y0, blkcnt = self.x0, self.y0, self.blkcnt
        return all(blkcnt[by - y0, bx - x0] >= STACK_CAP for bx, by in cells)

    def _add(self, obj: tuple[int, int, int, int], cells: list[Tile]) -> None:
        x0, y0, blkcnt = self.x0, self.y0, self.blkcnt
        x, y, c, _ii = obj
        self.objs.append(obj)
        self.ncat[c] += 1
        self.C[c, y - y0 + RINT, x - x0 + RINT] += 1
        for bx, by in cells:
            blkcnt[by - y0, bx - x0] += 1
            if blkcnt[by - y0, bx - x0] == 1:
                self.nblocked += 1

    def _death(self) -> None:
        rng = self.rng
        n = len(self.objs)
        if n == 0:
            return
        j = rng.randrange(n)
        x, y, c, ii = self.objs[j]
        lam_star = self._lam_star(c, x, y, True)
        acc = (n * _f(self.qc, c)) / max(lam_star * self.Nt, 1e-300)
        if rng.random() < acc and self.frees_connected(
            [(x + dx, y + dy) for dx, dy in self.model.iblk[c][ii]]
        ):
            self._remove(j)

    def _remove(self, j: int) -> None:
        x0, y0, blkcnt, objs = self.x0, self.y0, self.blkcnt, self.objs
        x, y, c, ii = objs[j]
        objs[j] = objs[-1]
        _ = objs.pop()
        self.ncat[c] -= 1
        self.C[c, y - y0 + RINT, x - x0 + RINT] -= 1
        for dx, dy in self.model.iblk[c][ii]:
            bx, by = x + dx - x0, y + dy - y0
            blkcnt[by, bx] -= 1
            if blkcnt[by, bx] == 0:
                self.nblocked -= 1

    def _result(self) -> tuple[list[PlacedObject], set[Tile], AbstractSet[Tile]]:
        x0, y0 = self.x0, self.y0
        out: list[PlacedObject] = []
        for x, y, c, ii in sorted(self.objs, key=lambda o: (o[1], o[0])):
            ident = self.model.idents[c][ii]
            out.append(PlacedObject.at(ident, (x, y), level=0, purpose=""))
        nz_y, nz_x = self.blkcnt.nonzero()
        ys_nz = cast(list[int], nz_y.tolist())
        xs_nz = cast(list[int], nz_x.tolist())
        blocked = {(x0 + lx, y0 + ly) for ly, lx in zip(ys_nz, xs_nz, strict=True)}
        return out, blocked, self.prot

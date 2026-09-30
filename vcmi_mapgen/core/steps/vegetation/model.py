"""The fitted per-terrain vegetation model both zone samplers draw from: the decoration
categories and their identity pools, the first-order intensities, the local interaction
kernel and the corpus coverage target."""

import collections
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.geometry import EBINS
from vcmi_mapgen.core.model import Identity, Tile
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.priors import vegetation as PS

RINT = 2
BASE_W = 0.3


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
    blk_cells: list[float]


def build_model(catalog: Catalog, terrain: str, st: PS.VegetationStats) -> VegModel:
    """Fitted per-terrain sampling model from the terrain's vegetation statistics ``st``:
    category list, intensities, theta kernel, ident pools, and each category's mean
    blocking cells."""
    th = PS.theta_local(st, rint=RINT)

    by_cat: collections.defaultdict[str, list[Identity]] = collections.defaultdict(list)
    for ident in catalog.decor(terrain):
        cat = catalog.decor_category(ident.kind)
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
        iweights.append([w.get(i.kind.lower(), 0) + BASE_W for i in ids])
        blk: list[list[Tile]] = []
        foot: list[list[Tile]] = []
        for i in ids:
            cells = [(cx, cy, b) for cx, cy, b in FP.anchored_cells(i.footprint, 0, 0)]
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
        blk_cells=[st.mean_blk_cells.get(c, 0.0) for c in cats],
    )

"""The spacing weight of a spot: how well a copy of a kind standing there fits the corpus law of
how far a copy stands from its nearest one."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import cast

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.priors.spacing import SpacingPriors
from vcmi_mapgen.core.reading.repeats import Kind, Spot, kind_key

FLOOR = 0.05
POINTS = 256

type Floats = NDArray[np.float64]
type Table = tuple[Floats, Floats, float, float]


@dataclass(slots=True)
class SpotWeight:
    """The weight of a spot for a kind, between FLOOR and 1. A spot at the normalised distance
    u from its nearest copy on its level weighs the fitted density of u over the density
    random placement gives it, scaled so the best u of the law weighs 1 and never below FLOOR,
    so no spot is shut out. ``counts`` holds the kind's copies on the finished map and ``land``
    the land tiles per level, so u reads as `copy_spacing` reads it, with the kind's count on a
    level taken as its share of the land. A spot with no copy on its level weighs what the law's
    ninetieth percentile does. A kind with fewer than two copies, or with no fit, weighs 1
    everywhere."""

    law: SpacingPriors
    counts: Mapping[Kind, int]
    land: Mapping[int, int]
    _tables: dict[str, Table | None] = field(default_factory=dict[str, Table | None])

    def spots(
        self,
        kind: Kind,
        purpose: str,
        cells: NDArray[np.int64],
        copies: Sequence[Spot],
    ) -> tuple[NDArray[np.float64], NDArray[np.bool_]]:
        """The weight of each spot, a row of ``cells`` holding its level, x and y, for a copy of
        ``kind`` of ``purpose``, and whether a copy there would stand crowded, its u under the
        tenth percentile of the fit. ``copies`` are the copies of the kind already standing."""
        levels, xs, ys = cells[:, 0], cells[:, 1], cells[:, 2]
        total = sum(self.land.values())
        table = self._table(kind, purpose)
        out = np.ones(len(xs), dtype=np.float64)
        crowded = np.zeros(len(xs), dtype=np.bool_)
        if table is None or self.counts.get(kind, 0) < 2 or total <= 0:
            return out, crowded
        grid, weight, cap, low = table
        for level in cast(list[int], np.unique(levels).tolist()):
            tiles = self.land.get(level, 0)
            if tiles <= 0:
                continue
            near: Floats = np.full(len(xs), np.inf)
            for lv, cx, cy in copies:
                if lv == level:
                    near = np.minimum(near, (xs - cx) ** 2.0 + (ys - cy) ** 2.0)
            n = self.counts[kind] * tiles / total
            u: Floats = n * np.pi * near / tiles
            here = np.equal(levels, level)
            out = np.where(here, np.interp(np.minimum(u, cap), grid, weight), out)
            crowded = np.where(here, u < low, crowded)
        return out, crowded

    def _table(self, kind: Kind, purpose: str) -> Table | None:
        key = kind_key(kind)
        if key not in self._tables:
            self._tables[key] = self._build(key, purpose)
        return self._tables[key]

    def _build(self, key: str, purpose: str) -> Table | None:
        fit = self.law.fit_for(key, purpose)
        if fit is None or fit.p90 <= 0:
            return None
        grid = np.linspace(0.0, fit.p90, POINTS)
        ratio = fit.density_of(grid) / np.exp(-grid)
        finite = np.isfinite(ratio)
        top = cast(float, ratio[finite].max(initial=0.0))
        if top <= 0:
            return None
        ratio = np.where(finite, ratio, top)
        peak = cast(float, ratio.max())
        return grid, np.maximum(ratio, FLOOR * peak) / peak, fit.p90, fit.p10

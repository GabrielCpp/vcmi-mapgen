"""The field sampler: decorations placed to cover the blocked mask a cellular field draws for
one zone, under the canvas's hard rules."""

import random
from typing import cast, final

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.grid.geometry import EBINS
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.planning.web import ZoneRef
from vcmi_mapgen.core.steps.vegetation.canvas import ZoneCanvas, zone_rng
from vcmi_mapgen.core.steps.vegetation.field.cellular import (
    cellular_field,
    coverage_by_ebin,
    target_mask,
)
from vcmi_mapgen.core.steps.vegetation.mix import ZoneMix
from vcmi_mapgen.core.steps.vegetation.model import VegModel
from vcmi_mapgen.core.steps.vegetation.sampler import SampleOptions, ZoneGrowth

FILL_TRIES = 12
FILL_CHECKS = 3


@final
class FieldSampler:
    def sample(self, zone: ZoneRef, model: VegModel, seed: int, opts: SampleOptions) -> ZoneGrowth:
        """Cover a cellular field's blocked mask with decorations in one zone, under the
        canvas's hard rules: nothing on `forbid` or the protected web, and no open ground
        walled off. The `border` tiles are part of the mask outright, so the zone front
        outside its entrance bands closes by construction, and the field shapes only the
        interior."""
        if not model.cats:
            return [], set(), set()
        return _FieldRun(ZoneCanvas(zone, model, opts), model, zone_rng(zone, seed)).fill()


def _edge_profile(model: VegModel) -> list[float]:
    """The corpus blocked mass per edge bin: each category's intensity in that bin times its
    mean blocking cells, summed over the categories."""
    return [
        sum(model.L[c, e] * model.blk_cells[c] for c in range(len(model.cats)))
        for e in range(EBINS)
    ]


@final
class _FieldRun:
    def __init__(self, canvas: ZoneCanvas, model: VegModel, rng: random.Random) -> None:
        self.canvas: ZoneCanvas = canvas
        self.model: VegModel = model
        self.rng: random.Random = rng
        self.mix: ZoneMix = ZoneMix(model, canvas.tiles_per_ebin, rng)

    def fill(self) -> ZoneGrowth:
        """Place decorations until the field's target mask is covered, one uncovered target
        tile at a time: draw a category from the corpus mix, try FILL_TRIES identities and
        offsets that block that tile, and keep the one that blocks the most uncovered target
        tiles for the fewest uncovered tiles off the mask."""
        cv = self.canvas
        dom = cv.inz & ~cv.protm & ~cv.box_mask(cv.forbid)
        tiles_per_ebin = np.bincount(cv.eb[dom].ravel(), minlength=EBINS)
        profile = np.array(_edge_profile(self.model))
        coverage = coverage_by_ebin(profile, tiles_per_ebin, self.model.target)
        field = cellular_field(cv.W, cv.H, self.rng)
        target = target_mask(field, dom, cv.eb, coverage, cv.border)
        ys, xs = target.nonzero()
        order = [
            (cv.x0 + lx, cv.y0 + ly)
            for ly, lx in zip(
                cast(list[int], ys.tolist()), cast(list[int], xs.tolist()), strict=True
            )
        ]
        self.rng.shuffle(order)
        for t in order:
            if cv.blkcnt[t[1] - cv.y0, t[0] - cv.x0] == 0:
                self._fill_tile(t, target)
        return cv.result()

    def _fill_tile(self, t: Tile, target: NDArray[np.bool_]) -> None:
        rng, model, cv = self.rng, self.model, self.canvas
        c = self.mix.draw_category()
        scored: list[tuple[int, int, int, int, int, list[Tile]]] = []
        for k in range(FILL_TRIES):
            ii = self.mix.draw_identity(c)
            if not model.iblk[c][ii]:
                continue
            dx, dy = rng.choice(model.iblk[c][ii])
            x, y = t[0] - dx, t[1] - dy
            if not self._in_zone(x, y) or (x, y) in cv.forbid:
                continue
            cells = cv.blocked_cells(c, ii, x, y)
            if cells is None:
                continue
            score = self._fill_score(cells, target)
            if score >= 0:
                scored.append((score, -k, x, y, ii, cells))
        scored.sort(reverse=True)
        for _score, _k, x, y, ii, cells in scored[:FILL_CHECKS]:
            if cv.try_place((x, y, c, ii), cells):
                return

    def _in_zone(self, x: int, y: int) -> bool:
        cv = self.canvas
        lx, ly = x - cv.x0, y - cv.y0
        return 0 <= lx < cv.W and 0 <= ly < cv.H and bool(cast(np.bool_, cv.inz[ly, lx]))

    def _fill_score(self, cells: list[Tile], target: NDArray[np.bool_]) -> int:
        cv = self.canvas
        gain = spill = 0
        for bx, by in cells:
            lx, ly = bx - cv.x0, by - cv.y0
            if cv.blkcnt[ly, lx] == 0:
                if target[ly, lx]:
                    gain += 1
                else:
                    spill += 1
        return gain - spill if gain else -1

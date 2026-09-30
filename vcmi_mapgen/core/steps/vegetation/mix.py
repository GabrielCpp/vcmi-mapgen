"""The zone mix: how many decorations of each category a zone expects, and the draws of a
category and an identity from that mix."""

import random
from typing import cast

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.steps.vegetation.model import VegModel


class ZoneMix:
    """The corpus-expected category counts of a zone with `tiles_per_ebin` tiles in each edge
    bin, and the draws `rng` makes from them."""

    def __init__(
        self, model: VegModel, tiles_per_ebin: NDArray[np.int64], rng: random.Random
    ) -> None:
        self.model: VegModel = model
        self.rng: random.Random = rng
        self.A: int = len(model.cats)
        self.nexp: NDArray[np.float64] = cast(
            NDArray[np.float64], (model.L * tiles_per_ebin[None, :]).sum(axis=1)
        )
        self.qc: NDArray[np.float64] = cast(NDArray[np.float64], self.nexp / self.nexp.sum())
        self.qc_cum: NDArray[np.float64] = np.cumsum(self.qc)

    def draw_category(self) -> int:
        """A category drawn from the zone's corpus-expected mix."""
        return min(int(np.searchsorted(self.qc_cum, self.rng.random())), self.A - 1)

    def draw_identity(self, c: int) -> int:
        """An identity of category `c` drawn by corpus frequency."""
        ws = self.model.iweights[c]
        return self.rng.choices(range(len(ws)), weights=ws, k=1)[0]

"""Fit the corpus curve of the resource mine count over each map's land area and player
count."""

from collections.abc import Sequence
from typing import cast

import numpy as np

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.priors.mines import MineCurve
from vcmi_mapgen.core.reading.families import Families
from vcmi_mapgen.core.reading.mines import MapMeasure, land_area, resource_mines


def map_mines(catalog: Catalog, state: MapState) -> int:
    """The resource mines on ``state``."""
    families = Families.of(catalog)
    return resource_mines(families.family(catalog, o) for o in state.objs)


def fit_curve(rows: Sequence[tuple[MapMeasure, int]]) -> MineCurve:
    """The least squares fit of log mines on log land and log players over the ``rows``
    holding a mine, with the intercept raised by half the residual variance."""
    kept = [(m, n) for m, n in rows if n > 0 and m.land > 0 and m.players > 0]
    x = np.array([[1.0, np.log(m.land), np.log(m.players)] for m, _n in kept])
    y = np.array([np.log(n) for _m, n in kept])
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    resid = y - x @ beta
    var = float(resid @ resid) / max(len(kept) - x.shape[1], 1)
    b0, b1, b2 = cast("list[float]", beta.tolist())
    return MineCurve(b0 + var / 2, b1, b2)


def mine_curve(catalog: Catalog, maps: Sequence[MapState], players: Sequence[int]) -> MineCurve:
    """The resource mine curve over the corpus ``maps``, each made for its ``players``."""
    rows = [
        (MapMeasure(land_area(m), p), map_mines(catalog, m))
        for m, p in zip(maps, players, strict=True)
    ]
    return fit_curve(rows)

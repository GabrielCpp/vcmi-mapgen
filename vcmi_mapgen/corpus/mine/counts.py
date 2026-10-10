"""Fit the corpus curves of the resource mine count and the town count over each map's land
area and player count."""

from collections.abc import Callable, Sequence
from typing import cast

import numpy as np

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.priors.counts import CountCurve
from vcmi_mapgen.core.reading.families import Families
from vcmi_mapgen.core.reading.ground import purpose_of
from vcmi_mapgen.core.reading.mines import MapMeasure, land_area, resource_mines


def map_mines(catalog: Catalog, state: MapState) -> int:
    """The resource mines on ``state``."""
    families = Families.of(catalog)
    return resource_mines(families.family(catalog, o) for o in state.objs)


def map_towns(catalog: Catalog, state: MapState) -> int:
    """The towns on ``state``, the player towns among them."""
    return sum(purpose_of(catalog, o) == Purpose.TOWN for o in state.objs)


def fit_curve(rows: Sequence[tuple[MapMeasure, int]]) -> CountCurve:
    """The least squares fit of log count on log land and log players over the ``rows``
    holding at least one, with the intercept raised by half the residual variance."""
    kept = [(m, n) for m, n in rows if n > 0 and m.land > 0 and m.players > 0]
    x = np.array([[1.0, np.log(m.land), np.log(m.players)] for m, _n in kept])
    y = np.array([np.log(n) for _m, n in kept])
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    resid = y - x @ beta
    var = float(resid @ resid) / max(len(kept) - x.shape[1], 1)
    b0, b1, b2 = cast("list[float]", beta.tolist())
    return CountCurve(b0 + var / 2, b1, b2)


def _curve(
    count: Callable[[Catalog, MapState], int],
    catalog: Catalog,
    maps: Sequence[MapState],
    players: Sequence[int],
) -> CountCurve:
    rows = [
        (MapMeasure(land_area(m), p), count(catalog, m)) for m, p in zip(maps, players, strict=True)
    ]
    return fit_curve(rows)


def mine_curve(catalog: Catalog, maps: Sequence[MapState], players: Sequence[int]) -> CountCurve:
    """The resource mine curve over the corpus ``maps``, each made for its ``players``."""
    return _curve(map_mines, catalog, maps, players)


def town_curve(catalog: Catalog, maps: Sequence[MapState], players: Sequence[int]) -> CountCurve:
    """The town curve over the corpus ``maps``, each made for its ``players``."""
    return _curve(map_towns, catalog, maps, players)

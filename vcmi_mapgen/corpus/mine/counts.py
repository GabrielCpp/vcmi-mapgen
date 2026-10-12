"""Fit the corpus curve of the town count over each map's land area and player count, of the
resource mine count over its land area, and of every gameplay family its count curve over its
land area, the power its efforts from home stretch by with the land and its guard record."""

import statistics
from collections.abc import Mapping, Sequence
from typing import cast

import numpy as np
from numpy.typing import NDArray
from scipy import optimize
from scipy.special import gammaln

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.priors.counts import CountCurve, FamilyCurves, FamilyFit
from vcmi_mapgen.core.reading.families import (
    TOP_LEVEL,
    Families,
    door_guard,
    family_days,
    family_purpose,
    guard_levels,
)
from vcmi_mapgen.core.reading.ground import purpose_of
from vcmi_mapgen.core.reading.mines import MapMeasure, land_area, resource_mines
from vcmi_mapgen.corpus.mine.effort import TownKey, home_spots

type Floats = NDArray[np.float64]

MIN_MAPS = 20
LAND_CAP = 1.0


def map_mines(catalog: Catalog, state: MapState) -> int:
    """The resource mines on ``state``."""
    families = Families.of(catalog)
    return resource_mines(families.family(catalog, o) for o in state.objs)


def map_towns(catalog: Catalog, state: MapState) -> int:
    """The towns on ``state``, the player towns among them."""
    return sum(purpose_of(catalog, o) == Purpose.TOWN for o in state.objs)


def _log_fit(x: Floats, y: Floats) -> tuple[list[float], float]:
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    resid = y - x @ beta
    var = float(resid @ resid) / max(len(y) - x.shape[1], 1)
    return cast("list[float]", beta.tolist()), var


def fit_curve(rows: Sequence[tuple[MapMeasure, int]]) -> CountCurve:
    """The least squares fit of log count on log land and log players over the ``rows``
    holding at least one, with the intercept raised by half the residual variance."""
    kept = [(m, n) for m, n in rows if n > 0 and m.land > 0 and m.players > 0]
    x = np.array([[1.0, np.log(m.land), np.log(m.players)] for m, _n in kept])
    (b0, b1, b2), var = _log_fit(x, np.array([np.log(n) for _m, n in kept]))
    return CountCurve(b0 + var / 2, b1, b2)


def fit_land_curve(rows: Sequence[tuple[int, int]]) -> CountCurve:
    """The least squares fit of log count on log land over the ``(land, count)`` rows holding
    at least one, with the intercept raised by half the residual variance."""
    kept = [(land, n) for land, n in rows if n > 0 and land > 0]
    x = np.array([[1.0, np.log(land)] for land, _n in kept])
    (b0, b1), var = _log_fit(x, np.array([np.log(n) for _land, n in kept]))
    return CountCurve(b0 + var / 2, b1, 0.0)


def mine_curve(catalog: Catalog, maps: Sequence[MapState]) -> CountCurve:
    """The resource mine curve over the land of the corpus ``maps``."""
    return fit_land_curve([(land_area(m), map_mines(catalog, m)) for m in maps])


def town_curve(catalog: Catalog, maps: Sequence[MapState], players: Sequence[int]) -> CountCurve:
    """The town curve over the corpus ``maps``, each made for its ``players``."""
    rows = [
        (MapMeasure(land_area(m), p), map_towns(catalog, m))
        for m, p in zip(maps, players, strict=True)
    ]
    return fit_curve(rows)


def _negbin_loss(params: Floats, y: Floats, x: Floats, offset: Floats) -> float:
    beta = params[:-1]
    r = np.exp(-params[-1:])
    mu = np.exp(offset + x @ beta)
    ll = (
        gammaln(y + r)
        - gammaln(r)
        - gammaln(y + 1)
        + r * np.log(r / (r + mu))
        + y * np.log(mu / (r + mu))
    )
    return -float(np.sum(ll))


def _negbin(y: Floats, x: Floats, offset: Floats) -> list[float]:
    beta0 = np.linalg.lstsq(x, np.log(y + 0.5) - offset, rcond=None)[0]
    start = np.concatenate([beta0, [0.0]])
    res = optimize.minimize(
        _negbin_loss,
        start,
        args=(y, x, offset),
        method="Nelder-Mead",
        options={"maxiter": 20000, "xatol": 1e-6, "fatol": 1e-8},
    )
    return cast("list[float]", np.asarray(res.x).tolist())


def fit_count(land: Sequence[int], counts: Sequence[int], cap: float | None = None) -> CountCurve:
    """The negative binomial fit of ``counts`` on log land over every map, the maps holding
    none included. A land exponent above ``cap`` is pinned at it and the intercept refitted,
    so a count the corpus shows saturating does not outgrow the map."""
    y = np.asarray(counts, dtype=np.float64)
    log_land = np.log(np.asarray(land, dtype=np.float64))
    ones = np.ones(len(y))
    b0, b1, _a = _negbin(y, np.column_stack([ones, log_land]), np.zeros(len(y)))
    if cap is None or b1 <= cap:
        return CountCurve(b0, b1, 0.0)
    b0, _a = _negbin(y, ones[:, None], cap * log_land)
    return CountCurve(b0, cap, 0.0)


def fit_stretch(land: Sequence[int], days: Sequence[int]) -> float:
    """The least squares slope of log(1 + days) on log land over the objects, each on the
    map of ``land`` tiles: the power the family's effort from home grows by with the land."""
    x = np.column_stack([np.ones(len(days)), np.log(np.asarray(land, dtype=np.float64))])
    z = np.log1p(np.asarray(days, dtype=np.float64))
    beta = np.linalg.lstsq(x, z, rcond=None)[0]
    _b0, b1 = cast("list[float]", beta.tolist())
    return b1


def guard_record(levels: Sequence[int]) -> tuple[float, ...]:
    """The share of ``levels`` at each guard level from 0 to TOP_LEVEL, a stronger guard
    counted at TOP_LEVEL."""
    counts = [0] * (TOP_LEVEL + 1)
    for level in levels:
        counts[min(max(level, 0), TOP_LEVEL)] += 1
    total = sum(counts)
    return tuple(n / total for n in counts) if total else ()


def _own_guards(
    catalog: Catalog, state: MapState, skip: Mapping[TownKey, int]
) -> list[tuple[str, int]]:
    families = Families.of(catalog)
    guards = guard_levels(catalog, state.objs)
    return [
        (f, door_guard(guards, o))
        for o in state.objs
        if (o.x, o.y, o.level) not in skip and (f := families.family(catalog, o)) is not None
    ]


def _land_cap(family: str) -> float | None:
    return None if family_purpose(family) == Purpose.DWELLING else LAND_CAP


def family_curves(
    catalog: Catalog,
    maps: Sequence[MapState],
    players: Sequence[int],
    owners: Sequence[Mapping[TownKey, int]],
    toll: Sequence[int],
) -> FamilyCurves:
    """The fit over land of every gameplay family seen on at least MIN_MAPS corpus maps made
    for some players, read against the median land of those maps, with the guard record of
    its objects outside the player towns."""
    lands: list[int] = []
    per_map: list[dict[str, int]] = []
    efforts: dict[str, list[tuple[int, int]]] = {}
    guards: dict[str, list[int]] = {}
    for state, p, own in zip(maps, players, owners, strict=True):
        if p <= 0:
            continue
        land = land_area(state)
        lands.append(land)
        counts: dict[str, int] = {}
        for family, days in family_days(catalog, state, home_spots(state, own), set(own), toll):
            counts[family] = counts.get(family, 0) + 1
            efforts.setdefault(family, []).append((land, days))
        per_map.append(counts)
        for family, level in _own_guards(catalog, state, own):
            guards.setdefault(family, []).append(level)
    fits: dict[str, FamilyFit] = {}
    for family, rows in sorted(efforts.items()):
        ns = [m.get(family, 0) for m in per_map]
        if sum(n > 0 for n in ns) < MIN_MAPS:
            continue
        curve = fit_count(lands, ns, _land_cap(family))
        stretch = fit_stretch([land for land, _d in rows], [d for _l, d in rows])
        fits[family] = FamilyFit(curve, stretch, guard_record(guards.get(family, [])))
    land_ref = int(statistics.median(lands)) if lands else 0
    return FamilyCurves(land_ref, fits)

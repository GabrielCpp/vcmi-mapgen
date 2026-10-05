"""Fit the logistic odds of water on each surface tile over every corpus map with water, and
keep each corpus map's water target."""

from collections.abc import Sequence
from typing import cast

import numpy as np

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.priors.water import WaterPriors, WaterTarget
from vcmi_mapgen.core.reading.ground import read_ground
from vcmi_mapgen.core.reading.places import read_places
from vcmi_mapgen.core.reading.water import (
    STATIC,
    Floats,
    Mask,
    land_labels,
    neighbour_features,
    static_features,
    water_places,
    water_target,
)

MIN_WATER = 0.02
RIDGE = 1e-3
ITERATIONS = 30


def map_rows(catalog: Catalog, state: MapState) -> tuple[WaterTarget, tuple[Floats, Floats] | None]:
    """One surface's water target, and its feature rows and water labels over every tile
    off the rock when it holds water."""
    grid = np.array([[t.value for t in row] for row in state.terrain[0]], dtype=np.int64)
    water = cast("Mask", grid == Terrain.WATER.value)
    rock = cast("Mask", grid == Terrain.ROCK.value)
    target = water_target(water, rock)
    ground = read_ground(catalog, state, 0)
    if target.share < MIN_WATER or ground is None:
        return target, None
    places = water_places(read_places(ground, {}).labels, land_labels(~water & ~rock))
    if not places:
        return target, None
    towns = [t.cells[len(t.cells) // 2] for t in ground.towns]
    shape = (grid.shape[0], grid.shape[1])
    x = np.concatenate(
        [static_features(shape, places, towns, target.edge), neighbour_features(water)], axis=1
    )
    keep = ~rock.ravel()
    return target, (x[keep], water.ravel()[keep].astype(np.float64))


def irls(x: Floats, y: Floats) -> Floats:
    """The ridge-regularised logistic coefficients of ``y`` on ``x`` by Newton steps."""
    beta: Floats = np.zeros(x.shape[1])
    for _ in range(ITERATIONS):
        p: Floats = 1 / (1 + np.exp(-(x @ beta)))
        weight = p * (1 - p) + 1e-9
        grad = cast("Floats", x.T @ (y - p)) - RIDGE * beta
        hess = cast("Floats", (x * weight[:, None]).T @ x) + RIDGE * np.eye(x.shape[1])
        step = np.linalg.solve(hess, grad)
        beta = beta + step
        if np.all(np.abs(step) < 1e-6):
            break
    return beta


def mine_water(catalog: Catalog, maps: Sequence[MapState]) -> WaterPriors:
    targets: list[WaterTarget] = []
    xs: list[Floats] = []
    ys: list[Floats] = []
    for state in maps:
        target, rows = map_rows(catalog, state)
        targets.append(target)
        if rows is not None:
            xs.append(rows[0])
            ys.append(rows[1])
    x, y = np.concatenate(xs), np.concatenate(ys)
    beta = irls(x, y)
    static_beta = irls(x[:, :STATIC], y)
    return WaterPriors(
        tuple(cast("list[float]", beta.tolist())),
        tuple(cast("list[float]", static_beta.tolist())),
        tuple(targets),
    )

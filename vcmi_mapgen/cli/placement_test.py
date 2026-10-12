"""The map-wide gameplay pass stands at least 1 - STOOD_TOL of the objects its plan asks for,
and keeps every family's median effort inside the corpus p10 to p90."""

import contextlib
import io
import statistics
from collections import defaultdict

import pytest

from vcmi_mapgen.cli.steps import StepConfig, build_steps
from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.pipeline import ProviderRegistry
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.reading.families import family_days
from vcmi_mapgen.core.reading.routes import Spot
from vcmi_mapgen.core.steps.gameplay.result import GameplayResult, Shortfall

SWEEP_SEEDS = range(1, 11)
STOOD_TOL = 0.1
LOW, HIGH = 0.1, 0.9


_MAPS: dict[StepConfig, tuple[MapState, Shortfall]] = {}


def _map(catalog: Catalog, priors: Priors, config: StepConfig) -> tuple[MapState, Shortfall]:
    if config in _MAPS:
        return _MAPS[config]
    state = MapState(size=config.size)
    ctx = ProviderRegistry()
    with contextlib.redirect_stdout(io.StringIO()):
        for name, step in build_steps(priors, config):
            step.inject(ctx)
            step.run(catalog, state)
            if name == "gameplay":
                break
    _MAPS[config] = (state, ctx.require(GameplayResult).shortfall)
    return _MAPS[config]


def _stood(catalog: Catalog, priors: Priors, config: StepConfig) -> float:
    _state, short = _map(catalog, priors, config)
    wanted = sum(short.wanted.values())
    return sum(short.placed.values()) / wanted if wanted else 1.0


def _quantile(hist: tuple[int, ...], q: float) -> int:
    total, acc = sum(hist), 0
    for day, n in enumerate(hist):
        acc += n
        if acc >= q * total:
            return day
    return len(hist) - 1


def test_a_small_map_stands_what_its_plan_asks(catalog: Catalog, priors: Priors) -> None:
    assert _stood(catalog, priors, StepConfig(3, 48)) >= 1 - STOOD_TOL


@pytest.mark.slow
def test_every_seed_stands_its_plan_at_the_corpus_effort(catalog: Catalog, priors: Priors) -> None:
    configs = [StepConfig(seed, 72) for seed in SWEEP_SEEDS]
    short = [
        (c.seed, round(r, 2)) for c in configs if (r := _stood(catalog, priors, c)) < 1 - STOOD_TOL
    ]
    assert short == []
    days: dict[str, list[int]] = defaultdict(list)
    for config in configs:
        state, _short = _map(catalog, priors, config)
        homes = [Spot(o.level, o.x, o.y) for o in state.player_towns]
        skip = {(o.x, o.y, o.level) for o in state.player_towns}
        for f, d in family_days(catalog, state, homes, skip, priors.effort.toll):
            days[f].append(d)
    outside = [
        (f, median, low, high)
        for f, ds in sorted(days.items())
        if (hist := priors.effort.families.get(f))
        and not (
            (low := _quantile(hist, LOW))
            <= (median := statistics.median_low(ds))
            <= (high := _quantile(hist, HIGH))
        )
    ]
    assert outside == []

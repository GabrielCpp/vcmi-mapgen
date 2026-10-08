"""Every player reaches a mine of each basic resource within PROMISE_DAYS hero-days of its
town, the players stay within PROMISE_GAP days of each other, and no gold mine stands that
near."""

import contextlib
import io

import pytest

from vcmi_mapgen.cli.steps import StepConfig, build_steps
from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.pipeline import ProviderRegistry
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.reading.promise import PROMISE_DAYS, promise_of
from vcmi_mapgen.core.steps.gameplay.economy import BASIC_MINE_RES

GOLD = "goldMine"
SWEEP_SEEDS = range(1, 11)


def _breaches(catalog: Catalog, priors: Priors, config: StepConfig) -> list[str]:
    state = MapState(size=config.size)
    ctx = ProviderRegistry()
    with contextlib.redirect_stdout(io.StringIO()):
        for _name, step in build_steps(priors, config):
            step.inject(ctx)
            step.run(catalog, state)
    basic = promise_of(catalog, state, BASIC_MINE_RES, priors.effort.toll).broken()
    gold = promise_of(catalog, state, (GOLD,), priors.effort.toll)
    near = [
        f"player {p} {GOLD}: {d[GOLD]} days"
        for p, d in enumerate(gold.days)
        if (v := d[GOLD]) is not None and v <= PROMISE_DAYS
    ]
    return basic + near


def test_a_small_map_keeps_the_mine_promise(catalog: Catalog, priors: Priors) -> None:
    assert _breaches(catalog, priors, StepConfig(3, 48)) == []


@pytest.mark.slow
@pytest.mark.parametrize("seed", SWEEP_SEEDS)
def test_every_seed_keeps_the_mine_promise(catalog: Catalog, priors: Priors, seed: int) -> None:
    assert _breaches(catalog, priors, StepConfig(seed, 72)) == []

"""CompensationStep on a small four-player map whose players claim uneven value: each prize
serves a player below the bar, that player reaches it first, and no prize puts a reward
placed before it more than a day further from any player."""

import contextlib
import io
from dataclasses import dataclass

import pytest

from vcmi_mapgen.cli.steps import StepConfig, build_steps
from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.pipeline import ProviderRegistry
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.reading.claimed import Claim, claimed, claims_of, owner_maps
from vcmi_mapgen.core.reading.places import owners_of
from vcmi_mapgen.core.steps.compensation.prize import BAR, deficits
from vcmi_mapgen.core.steps.compensation.result import CompensationResult

CONFIG = StepConfig(seed=2, size=48, players=4)


@dataclass(frozen=True, slots=True)
class Run:
    before: list[Claim]
    after: list[Claim]
    result: CompensationResult


def _claims(catalog: Catalog, priors: Priors, state: MapState) -> list[Claim]:
    maps = owner_maps(catalog, state, owners_of(state), priors.effort.toll)
    return claims_of(catalog, state, maps)


@pytest.fixture(scope="module")
def run(catalog: Catalog, priors: Priors) -> Run:
    state = MapState(size=CONFIG.size)
    ctx = ProviderRegistry()
    before: list[Claim] = []
    with contextlib.redirect_stdout(io.StringIO()):
        for name, step in build_steps(priors, CONFIG):
            step.inject(ctx)
            if name == "compensation":
                before = _claims(catalog, priors, state)
            step.run(catalog, state)
            if name == "compensation":
                break
    result = ctx.require(CompensationResult)
    return Run(before, _claims(catalog, priors, state), result)


def test_each_prize_serves_a_player_below_the_bar(run: Run) -> None:
    lacking = deficits(run.result.claimed, BAR)
    assert run.result.prizes
    assert all(lacking[p.player] > 0 for p in run.result.prizes)


def test_the_served_player_reaches_its_prize_first(run: Run) -> None:
    added = run.after[len(run.before) :]
    assert len(added) == len(run.result.prizes)
    for prize, claim in zip(run.result.prizes, added, strict=True):
        assert claim.days[prize.player] == prize.days
        rivals = [d for i, d in enumerate(claim.days) if i != prize.player and d is not None]
        assert all(d > prize.days for d in rivals)


def test_no_prize_puts_an_earlier_reward_two_days_further(run: Run) -> None:
    for old, new in zip(run.before, run.after, strict=False):
        for d0, d1 in zip(old.days, new.days, strict=True):
            assert (d0 is None) == (d1 is None)
            assert d0 is None or d1 is None or d0 <= d1 <= d0 + 1


def test_the_prizes_raise_the_worst_share(run: Run) -> None:
    worst = max(BAR)
    before = run.result.claimed[worst]
    after = claimed(run.after, worst)
    assert min(after) / max(after) > min(before) / max(before)

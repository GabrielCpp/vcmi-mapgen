"""Generated maps hem their towns, mines, dwellings, banks and visited objects at the corpus
rate: within HEMMED_SPREAD of HEMMED_SHARE on nine levels in ten. Hand-made maps spread wider."""

import contextlib
import io

import pytest

from vcmi_mapgen.cli.steps import StepConfig, build_steps
from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.pipeline import ProviderRegistry
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.priors.gameplay import HEMMED_SHARE
from vcmi_mapgen.core.reading.flanks import read_hemmed

HEMMED_SPREAD = 0.1
MODELS = ("places", "markov")
SWEEP_SEEDS = range(1, 11)


def _shares(catalog: Catalog, priors: Priors, config: StepConfig) -> list[float]:
    state = MapState(size=config.size)
    ctx = ProviderRegistry()
    with contextlib.redirect_stdout(io.StringIO()):
        for _name, step in build_steps(priors, config):
            step.inject(ctx)
            step.run(catalog, state)
    hemmed = [read_hemmed(catalog, state, level) for level in sorted(state.terrain)]
    return [h.share for h in hemmed if h.share is not None]


def _off(shares: list[float]) -> list[float]:
    return [s for s in shares if abs(s - HEMMED_SHARE) > HEMMED_SPREAD]


@pytest.mark.parametrize("model", MODELS)
def test_a_small_map_hems_its_objects(catalog: Catalog, priors: Priors, model: str) -> None:
    shares = _shares(catalog, priors, StepConfig(3, 48, terrain=model))
    assert shares
    assert _off(shares) == []


@pytest.mark.slow
@pytest.mark.parametrize("model", MODELS)
def test_nine_levels_in_ten_hem_their_objects(catalog: Catalog, priors: Priors, model: str) -> None:
    shares: list[float] = []
    for seed in SWEEP_SEEDS:
        config = StepConfig(seed, 72, terrain=model, subterrain=seed % 2 == 0)
        shares += _shares(catalog, priors, config)
    assert len(_off(shares)) <= len(shares) // 10, _off(shares)

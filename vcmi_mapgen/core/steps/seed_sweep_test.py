"""The generator finishes every seed of a small sweep and never removes an earlier object, save
the decorations a step lifts to make room for its own objects."""

import contextlib
import io

import pytest

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.model.purpose import DECOR
from vcmi_mapgen.core.pipeline import ProviderRegistry
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.steps.steps_write_map_test import SIZE, pipeline_steps

SWEEP_SEEDS = range(1, 13)


@pytest.mark.slow
@pytest.mark.parametrize("seed", SWEEP_SEEDS)
def test_the_generator_finishes_the_seed_additively(
    catalog: Catalog, priors: Priors, seed: int
) -> None:
    state = MapState(size=SIZE)
    ctx = ProviderRegistry()
    with contextlib.redirect_stdout(io.StringIO()):
        for name, step in pipeline_steps(priors, seed):
            before = list(state.objs)
            step.inject(ctx)
            step.run(catalog, state)
            now = {id(o) for o in state.objs}
            kept = [o for o in before if id(o) in now]
            gone = [o for o in before if id(o) not in now]
            assert all(a is b for a, b in zip(state.objs, kept, strict=False)), name
            assert all(o.purpose in DECOR for o in gone), name

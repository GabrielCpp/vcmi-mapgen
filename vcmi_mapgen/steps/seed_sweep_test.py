"""The generator finishes every seed of a small sweep and never removes an earlier object."""

import contextlib
import io

import pytest

from vcmi_mapgen.models import MapState
from vcmi_mapgen.ontology import Ontology
from vcmi_mapgen.pipeline import ProviderRegistry
from vcmi_mapgen.steps.steps_write_map_test import SIZE, pipeline_steps

SWEEP_SEEDS = range(1, 13)


@pytest.mark.slow
@pytest.mark.parametrize("seed", SWEEP_SEEDS)
def test_the_generator_finishes_the_seed_additively(seed: int) -> None:
    ontology = Ontology()
    state = MapState(size=SIZE)
    ctx = ProviderRegistry()
    with contextlib.redirect_stdout(io.StringIO()):
        for name, step in pipeline_steps(seed):
            before = list(state.objs)
            step.inject(ctx)
            step.run(ontology, state)
            kept = state.objs[: len(before)]
            assert all(a is b for a, b in zip(kept, before, strict=True)), name

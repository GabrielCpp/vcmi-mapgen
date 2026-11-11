"""Generated maps tuck their mines, dwellings, banks and visited objects in as snug as hand-made
maps: per size class with at least MIN_OBJECTS objects, the snug share reaches SNUG_FLOOR on nine
maps in ten, as it does on hand-made maps."""

import contextlib
import io

import pytest

from vcmi_mapgen.cli.steps import StepConfig, build_steps
from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.snug import SIZE_CLASSES
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.pipeline import ProviderRegistry
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.priors.gameplay import SNUG_FLOOR
from vcmi_mapgen.core.reading.snug import Snug, read_snug

MIN_OBJECTS = 8
SWEEP_SEEDS = range(1, 11)


def _snug(catalog: Catalog, priors: Priors, config: StepConfig) -> Snug:
    state = MapState(size=config.size)
    ctx = ProviderRegistry()
    with contextlib.redirect_stdout(io.StringIO()):
        for _name, step in build_steps(priors, config):
            step.inject(ctx)
            step.run(catalog, state)
    out = Snug()
    for level in sorted(state.terrain):
        out = out + read_snug(catalog, state, level)
    return out


def _short(snug: Snug) -> dict[int, float]:
    return {
        size: share
        for size in SIZE_CLASSES
        if snug.objects[size] >= MIN_OBJECTS
        and (share := snug.share(size)) is not None
        and share < SNUG_FLOOR[size]
    }


def test_a_small_map_tucks_its_objects_in(catalog: Catalog, priors: Priors) -> None:
    snug = _snug(catalog, priors, StepConfig(3, 48))
    assert sum(snug.objects.values()) > 0
    assert _short(snug) == {}


@pytest.mark.slow
def test_nine_seeds_in_ten_tuck_their_objects_in(catalog: Catalog, priors: Priors) -> None:
    short: dict[int, dict[int, float]] = {}
    for seed in SWEEP_SEEDS:
        config = StepConfig(seed, 72, subterrain=seed % 2 == 0)
        if s := _short(_snug(catalog, priors, config)):
            short[seed] = s
    assert len(short) <= len(SWEEP_SEEDS) // 10, short

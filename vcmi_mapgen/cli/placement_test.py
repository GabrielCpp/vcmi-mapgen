"""The map-wide gameplay pass holds each family at the corpus rate per tile, within DENSITY_TOL,
keeps every family's median effort inside the corpus p10 to p90, and leaves each family's
reach per band at most REACH_GAP apart between the players."""

import contextlib
import io
import statistics
from collections import defaultdict

import pytest

from vcmi_mapgen.cli.steps import StepConfig, build_steps
from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState, PlacedObject
from vcmi_mapgen.core.model.purpose import FLANKED
from vcmi_mapgen.core.pipeline import ProviderRegistry
from vcmi_mapgen.core.placement.intensity import density
from vcmi_mapgen.core.planning.zone_plan import ZonePlan
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.priors.effort import BANDS
from vcmi_mapgen.core.reading.families import Families, family_days, unguarded
from vcmi_mapgen.core.reading.promise import doors, player_maps
from vcmi_mapgen.core.reading.routes import Spot
from vcmi_mapgen.core.steps.gameplay.reach import Reach

MODELS = ("places", "markov")
SWEEP_SEEDS = range(1, 11)
DENSITY_TOL = 0.1
REACH_GAP = 2
LOW, HIGH = 0.1, 0.9


_MAPS: dict[StepConfig, tuple[MapState, ZonePlan]] = {}


def _map(catalog: Catalog, priors: Priors, config: StepConfig) -> tuple[MapState, ZonePlan]:
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
    _MAPS[config] = (state, ctx.require(ZonePlan))
    return _MAPS[config]


def _placed(catalog: Catalog, state: MapState) -> list[tuple[str, PlacedObject]]:
    families = Families.of(catalog)
    homes = {id(o) for o in state.player_towns}
    return [
        (f, o)
        for o in state.objs
        if id(o) not in homes and (f := families.family(catalog, o)) is not None
    ]


def _density(catalog: Catalog, priors: Priors, config: StepConfig) -> float:
    state, plan = _map(catalog, priors, config)
    expected = sum(
        len(z.ts) * sum(density(priors.gameplay[level][z.terrain]).get(p, 0.0) for p in FLANKED)
        for level, levels in plan.levels.items()
        for z in levels.zones.values()
    )
    return len(_placed(catalog, state)) / expected


def _reach_gap(catalog: Catalog, priors: Priors, config: StepConfig) -> int:
    state, _plan = _map(catalog, priors, config)
    placed = _placed(catalog, state)
    view = unguarded(catalog, state, (o for _f, o in placed))
    maps = player_maps(catalog, view, priors.effort.toll)
    reach = Reach(len(maps))
    for f, o in placed:
        lows = (min((e.total for d in doors(o) if (e := em.visit(d))), default=None) for em in maps)
        reach.add(f, tuple(None if d is None else priors.effort.band(d) for d in lows))
    rows = [[reach.within(f, p) for p in range(len(maps))] for f in {f for f, _o in placed}]
    return max(
        (max(r[b] for r in fam) - min(r[b] for r in fam) for fam in rows for b in range(BANDS)),
        default=0,
    )


def _quantile(hist: tuple[int, ...], q: float) -> int:
    total, acc = sum(hist), 0
    for day, n in enumerate(hist):
        acc += n
        if acc >= q * total:
            return day
    return len(hist) - 1


def test_a_small_map_keeps_each_family_even_between_players(
    catalog: Catalog, priors: Priors
) -> None:
    assert _reach_gap(catalog, priors, StepConfig(3, 48)) <= REACH_GAP


@pytest.mark.slow
@pytest.mark.parametrize("model", MODELS)
def test_every_seed_holds_the_corpus_rate_and_effort_evenly(
    catalog: Catalog, priors: Priors, model: str
) -> None:
    configs = [StepConfig(seed, 72, terrain=model) for seed in SWEEP_SEEDS]
    sparse = [
        (c.seed, round(r, 2))
        for c in configs
        if abs((r := _density(catalog, priors, c)) - 1) > DENSITY_TOL
    ]
    uneven = [(c.seed, g) for c in configs if (g := _reach_gap(catalog, priors, c)) > REACH_GAP]
    assert (sparse, uneven) == ([], [])
    days: dict[str, list[int]] = defaultdict(list)
    for config in configs:
        state, _plan = _map(catalog, priors, config)
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

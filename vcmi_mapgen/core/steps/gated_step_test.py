"""Reliability tests for steps.gated.step (GatedStep) and TreasureStep after it."""

import contextlib
import io

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.pipeline import Pipeline
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.steps import (
    GameplayStep,
    GatedStep,
    TerrainStep,
    TreasureStep,
    VegetationStep,
)
from vcmi_mapgen.core.steps.vegetation.gibbs.sampler import GibbsSampler


def _run_through_treasure(catalog: Catalog, priors: Priors, seed: int) -> MapState:
    size, players = 48, 2
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        pipeline = Pipeline(catalog, size)
        _ = pipeline.add_step(TerrainStep(priors, size, seed, "normal", True))
        _ = pipeline.add_step(VegetationStep(priors, GibbsSampler(), seed, players))
        _ = pipeline.add_step(GameplayStep(priors, seed, players, size, True))
        _ = pipeline.add_step(GatedStep(priors, seed, size))
        _ = pipeline.add_step(TreasureStep(priors, seed, size))
        map_state = pipeline.run()
    return map_state


def test_loot_zone_sealing_never_drops_a_subterranean_gate(
    catalog: Catalog, priors: Priors
) -> None:
    """seed=7/size=48/subterrain places a Subterranean Gate pair whose (17, 14) tile falls
    inside a zone GatedStep seals as a loot zone. GatedStep and TreasureStep only add
    objects, so the gate pair must survive on both levels at the same (x, y)."""
    state = _run_through_treasure(catalog, priors, seed=7)
    gates_by_level: dict[int, list[tuple[int, int]]] = {0: [], 1: []}
    for o in state.objs:
        if catalog.identity_of(o.kind).type == "subterraneanGate":
            gates_by_level[o.level].append((o.x, o.y))
    assert gates_by_level[0], "fixture assumption broke: expected >= 1 gate pair on this seed"
    assert sorted(gates_by_level[0]) == sorted(gates_by_level[1]), (
        "a Subterranean Gate pair must exist on BOTH levels at the SAME (x, y) — "
        f"level 0 has {sorted(gates_by_level[0])}, level 1 has {sorted(gates_by_level[1])}"
    )

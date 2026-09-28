"""Reliability tests for steps.gated.step (GatedStep) and TreasureStep after it."""

import contextlib
import io

from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.pipeline import Pipeline
from vcmi_mapgen.core.steps import (
    GameplayStep,
    GatedStep,
    SegmentStep,
    TerrainStep,
    TreasureStep,
    VegetationStep,
)
from vcmi_mapgen.vcmi.catalog.adapter import Ontology


def _run_through_treasure(
    seed: int, size: int = 48, players: int = 2, subterrain: bool = True
) -> MapState:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        pipeline = Pipeline(Ontology(), size)
        _ = pipeline.add_step(
            TerrainStep(size=size, seed=seed, water_mode="normal", subterrain=subterrain)
        )
        _ = pipeline.add_step(SegmentStep())
        _ = pipeline.add_step(VegetationStep(seed=seed, players=players))
        _ = pipeline.add_step(
            GameplayStep(seed=seed, players=players, size=size, subterrain=subterrain)
        )
        _ = pipeline.add_step(GatedStep(seed=seed, size=size))
        _ = pipeline.add_step(TreasureStep(seed=seed, size=size))
        map_state = pipeline.run()
    return map_state


def test_loot_zone_sealing_never_drops_a_subterranean_gate() -> None:
    """seed=7/size=48/subterrain places a Subterranean Gate pair whose (17, 14) tile falls
    inside a zone GatedStep seals as a loot zone. GatedStep and TreasureStep only add
    objects, so the gate pair must survive on both levels at the same (x, y)."""
    state = _run_through_treasure(seed=7)
    gates_by_level: dict[int, list[tuple[int, int]]] = {0: [], 1: []}
    for o in state.objs:
        if o.type == "subterraneanGate":
            gates_by_level[o.level].append((o.x, o.y))
    assert gates_by_level[0], "fixture assumption broke: expected >= 1 gate pair on this seed"
    assert sorted(gates_by_level[0]) == sorted(gates_by_level[1]), (
        "a Subterranean Gate pair must exist on BOTH levels at the SAME (x, y) — "
        f"level 0 has {sorted(gates_by_level[0])}, level 1 has {sorted(gates_by_level[1])}"
    )

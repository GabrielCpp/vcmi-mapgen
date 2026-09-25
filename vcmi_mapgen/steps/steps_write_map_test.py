import contextlib
import io
from dataclasses import dataclass

import pytest

from vcmi_mapgen.kit.objects import mask_interactive_cells
from vcmi_mapgen.models import MapState
from vcmi_mapgen.ontology import Ontology
from vcmi_mapgen.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.steps import (
    BorderStep,
    GameplayStep,
    GateStep,
    LootStep,
    PickupStep,
    PortalStep,
    ScatterStep,
    SegmentStep,
    TerrainStep,
    VegetationStep,
)
from vcmi_mapgen.steps.pickup.scatter import guard_zoc
from vcmi_mapgen.validate import terrain_violations

SIZE = 48
SEED = 7
PLAYERS = 2


@dataclass(frozen=True, slots=True)
class Snapshot:
    objs: tuple[str, ...]
    cells: int
    surfs: int
    zones: int
    gate_blk: int
    player_towns: tuple[str, ...]


def _snapshot(state: MapState) -> Snapshot:
    return Snapshot(
        objs=tuple(repr(o) for o in state.objs),
        cells=len(state.cells),
        surfs=len(state.surfs),
        zones=sum(len(z) for z in state.zones.values()),
        gate_blk=sum(len(b) for b in state.gate_blk.values()),
        player_towns=tuple(repr(o) for o in state.player_towns),
    )


def _steps() -> list[tuple[str, PipelineStep]]:
    return [
        (
            "terrain_gen",
            TerrainStep(size=SIZE, seed=SEED, water_mode="normal", subterrain=True),
        ),
        ("segment", SegmentStep()),
        ("gate", GateStep(seed=SEED)),
        ("gameplay", GameplayStep(seed=SEED, players=PLAYERS, size=SIZE, subterrain=True)),
        ("vegetation", VegetationStep(seed=SEED)),
        ("pickup", PickupStep(seed=SEED, size=SIZE)),
        ("border", BorderStep(seed=SEED, size=SIZE)),
        ("portal", PortalStep(seed=SEED, size=SIZE)),
        ("loot", LootStep(seed=SEED, size=SIZE)),
        ("scatter", ScatterStep(seed=SEED, size=SIZE)),
    ]


@dataclass(frozen=True, slots=True)
class PipelineRun:
    ontology: Ontology
    state: MapState
    transitions: dict[str, tuple[Snapshot, Snapshot]]


@pytest.fixture(scope="module")
def pipeline_run() -> PipelineRun:
    ontology = Ontology()
    state = MapState(size=SIZE)
    ctx = ProviderRegistry()
    result: dict[str, tuple[Snapshot, Snapshot]] = {}
    with contextlib.redirect_stdout(io.StringIO()):
        for name, step in _steps():
            before = _snapshot(state)
            step.inject(ctx)
            step.run(ontology, state)
            result[name] = (before, _snapshot(state))
    return PipelineRun(ontology, state, result)


@pytest.fixture(scope="module")
def transitions(pipeline_run: PipelineRun) -> dict[str, tuple[Snapshot, Snapshot]]:
    return pipeline_run.transitions


def test_terrain_gen_writes_cells_and_surfs(
    transitions: dict[str, tuple[Snapshot, Snapshot]],
) -> None:
    before, after = transitions["terrain_gen"]
    assert (before.cells, before.surfs) == (0, 0)
    assert after.cells > 0
    assert after.surfs > 0


def test_segment_writes_zones(transitions: dict[str, tuple[Snapshot, Snapshot]]) -> None:
    before, after = transitions["segment"]
    assert before.zones == 0
    assert after.zones > 0


def test_gate_writes_gate_blk(transitions: dict[str, tuple[Snapshot, Snapshot]]) -> None:
    before, after = transitions["gate"]
    assert before.gate_blk == 0
    assert after.gate_blk > 0


def test_gameplay_writes_objs_and_player_towns(
    transitions: dict[str, tuple[Snapshot, Snapshot]],
) -> None:
    before, after = transitions["gameplay"]
    assert before.objs == ()
    assert before.player_towns == ()
    assert len(after.objs) > 0
    assert len(after.player_towns) > 0


@pytest.mark.parametrize("name", ["vegetation", "border", "loot", "scatter"])
def test_placement_steps_change_objs(
    transitions: dict[str, tuple[Snapshot, Snapshot]], name: str
) -> None:
    before, after = transitions[name]
    assert after.objs != before.objs


def test_no_object_stands_on_a_disallowed_terrain(pipeline_run: PipelineRun) -> None:
    violations = list(terrain_violations(pipeline_run.ontology, pipeline_run.state))
    assert violations == []


def test_no_guard_stands_on_a_mine_visit_tile(pipeline_run: PipelineRun) -> None:
    visit = {
        (o.level, tile)
        for o in pipeline_run.state.objs
        if o.purpose == "MINE"
        for tile in mask_interactive_cells(o.mask, o.x, o.y)
    }
    guards = [
        o
        for o in pipeline_run.state.objs
        if o.purpose == "GUARD" and (o.level, (o.x, o.y)) in visit
    ]
    assert guards == []


def test_scatter_piles_stay_out_of_every_guard_zone(pipeline_run: PipelineRun) -> None:
    for level in (0, 1):
        level_objs = [o for o in pipeline_run.state.objs if o.level == level]
        zoc = guard_zoc(level_objs)
        piles = [o for o in level_objs if o.purpose == "RESOURCE_PILE"]
        assert piles
        for o in piles:
            for cell in mask_interactive_cells(o.mask, o.x, o.y):
                assert cell not in zoc, f"pile at {cell} sits in a guard's zone of control"

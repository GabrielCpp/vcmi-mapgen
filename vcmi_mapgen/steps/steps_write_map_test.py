import contextlib
import io
from dataclasses import dataclass

import pytest

from vcmi_mapgen.kit.objects import mask_cells, mask_interactive_cells
from vcmi_mapgen.models import MapState, PlacedObject, Tile
from vcmi_mapgen.ontology import Ontology
from vcmi_mapgen.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.steps import (
    BorderStep,
    GameplayStep,
    GatedStep,
    LootStep,
    PortalStep,
    ScatterStep,
    SegmentStep,
    TerrainStep,
    TreasureStep,
    VegetationStep,
)
from vcmi_mapgen.steps.placement import guard_spaced, guard_zoc
from vcmi_mapgen.validate import terrain_violations

SIZE = 48
SEED = 7
PLAYERS = 2
VEGETATION_TOUCH_FLOOR = 0.8


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


def pipeline_steps(seed: int = SEED) -> list[tuple[str, PipelineStep]]:
    return [
        (
            "terrain_gen",
            TerrainStep(size=SIZE, seed=seed, water_mode="normal", subterrain=True),
        ),
        ("segment", SegmentStep()),
        ("vegetation", VegetationStep(seed=seed)),
        ("gameplay", GameplayStep(seed=seed, players=PLAYERS, size=SIZE, subterrain=True)),
        ("gated", GatedStep(seed=seed, size=SIZE)),
        ("treasure", TreasureStep(seed=seed, size=SIZE)),
        ("border", BorderStep(seed=seed, size=SIZE)),
        ("portal", PortalStep(seed=seed, size=SIZE)),
        ("loot", LootStep(seed=seed, size=SIZE)),
        ("scatter", ScatterStep(seed=seed, size=SIZE)),
    ]


@dataclass(frozen=True, slots=True)
class PipelineRun:
    ontology: Ontology
    state: MapState
    transitions: dict[str, tuple[Snapshot, Snapshot]]

    def added_by(self, name: str) -> list[PlacedObject]:
        before, after = self.transitions[name]
        return self.state.objs[len(before.objs) : len(after.objs)]


@pytest.fixture(scope="module")
def pipeline_run() -> PipelineRun:
    ontology = Ontology()
    state = MapState(size=SIZE)
    ctx = ProviderRegistry()
    result: dict[str, tuple[Snapshot, Snapshot]] = {}
    with contextlib.redirect_stdout(io.StringIO()):
        for name, step in pipeline_steps():
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


def test_gameplay_writes_gate_blk(transitions: dict[str, tuple[Snapshot, Snapshot]]) -> None:
    before, after = transitions["gameplay"]
    assert before.gate_blk == 0
    assert after.gate_blk > 0


def test_gameplay_writes_player_towns(
    transitions: dict[str, tuple[Snapshot, Snapshot]],
) -> None:
    before, after = transitions["gameplay"]
    assert before.player_towns == ()
    assert len(after.player_towns) == PLAYERS


@pytest.mark.parametrize("name", ["vegetation", "gameplay", "border", "loot", "scatter"])
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
        piles = [o for o in level_objs if o.purpose == "RESOURCE_PILE" and not o.cache]
        assert piles
        for o in piles:
            for cell in mask_interactive_cells(o.mask, o.x, o.y):
                assert cell not in zoc, f"pile at {cell} sits in a guard's zone of control"


@pytest.mark.parametrize("name", [name for name, _step in pipeline_steps()])
def test_every_step_keeps_the_objects_before_it(
    transitions: dict[str, tuple[Snapshot, Snapshot]], name: str
) -> None:
    before, after = transitions[name]
    assert after.objs[: len(before.objs)] == before.objs


@pytest.mark.parametrize("name", ["border", "loot"])
def test_a_late_guard_keeps_its_distance_from_every_other_guard(
    pipeline_run: PipelineRun, name: str
) -> None:
    guards = [o for o in pipeline_run.state.objs if o.purpose == "GUARD"]
    for g in (o for o in pipeline_run.added_by(name) if o.purpose == "GUARD"):
        others = [(o.x, o.y) for o in guards if o is not g and o.level == g.level]
        assert guard_spaced((g.x, g.y), others), f"{name} guard at {(g.x, g.y)} crowds another"


def _touches(o: PlacedObject, blocking: set[tuple[int, Tile]]) -> bool:
    return any(
        (o.level, (x + dx, y + dy)) in blocking
        for x, y, _b in mask_cells(o.mask, o.x, o.y)
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
    )


def test_gameplay_objects_sit_next_to_vegetation(pipeline_run: PipelineRun) -> None:
    blocking = {
        (o.level, (x, y))
        for o in pipeline_run.added_by("vegetation")
        for x, y, blk in mask_cells(o.mask, o.x, o.y)
        if blk
    }
    placed = [o for o in pipeline_run.added_by("gameplay") if o.purpose != "GUARD"]
    assert placed
    share = sum(_touches(o, blocking) for o in placed) / len(placed)
    assert share >= VEGETATION_TOUCH_FLOOR, f"only {share:.0%} of gameplay objects touch vegetation"

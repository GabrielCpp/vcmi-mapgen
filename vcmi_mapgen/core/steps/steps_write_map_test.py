import contextlib
import io
from dataclasses import dataclass

import pytest

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState, PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.core.placement.footprint import anchored_cells, interactive_cells
from vcmi_mapgen.core.placement.guards import guard_spaced, guard_zoc
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.steps import (
    GameplayStep,
    GatedStep,
    LootStep,
    PortalStep,
    ScatterStep,
    TerrainStep,
    TreasureStep,
    VegetationStep,
)
from vcmi_mapgen.core.steps.terrain_gen.markov import MarkovTerrain
from vcmi_mapgen.core.steps.terrain_gen.model import TerrainOptions
from vcmi_mapgen.core.steps.terrain_gen.result import Segmentation
from vcmi_mapgen.core.steps.vegetation.gibbs.sampler import GibbsSampler

SIZE = 48
SEED = 7
PLAYERS = 2
VEGETATION_TOUCH_FLOOR = 0.8


@dataclass(frozen=True, slots=True)
class Snapshot:
    objs: tuple[str, ...]
    terrain: int
    gate_blk: int
    player_towns: tuple[str, ...]


def _snapshot(state: MapState) -> Snapshot:
    return Snapshot(
        objs=tuple(repr(o) for o in state.objs),
        terrain=len(state.terrain),
        gate_blk=sum(len(b) for b in state.gate_blk.values()),
        player_towns=tuple(repr(o) for o in state.player_towns),
    )


STEP_NAMES = (
    "terrain_gen",
    "vegetation",
    "gameplay",
    "gated",
    "treasure",
    "portal",
    "loot",
    "scatter",
)


def pipeline_steps(priors: Priors, seed: int = SEED) -> list[tuple[str, PipelineStep]]:
    steps: list[PipelineStep] = [
        TerrainStep(priors, MarkovTerrain(), seed, TerrainOptions(SIZE, "normal", True, PLAYERS)),
        VegetationStep(priors, GibbsSampler(), seed, PLAYERS),
        GameplayStep(priors, seed, PLAYERS, True),
        GatedStep(priors, seed, SIZE),
        TreasureStep(priors, seed, SIZE),
        PortalStep(priors, seed, SIZE),
        LootStep(priors, seed, SIZE),
        ScatterStep(priors, seed, SIZE),
    ]
    return list(zip(STEP_NAMES, steps, strict=True))


@dataclass(frozen=True, slots=True)
class PipelineRun:
    catalog: Catalog
    state: MapState
    ctx: ProviderRegistry
    transitions: dict[str, tuple[Snapshot, Snapshot]]

    def added_by(self, name: str) -> list[PlacedObject]:
        before, after = self.transitions[name]
        return self.state.objs[len(before.objs) : len(after.objs)]


@pytest.fixture(scope="module")
def pipeline_run(catalog: Catalog, priors: Priors) -> PipelineRun:
    state = MapState(size=SIZE)
    ctx = ProviderRegistry()
    result: dict[str, tuple[Snapshot, Snapshot]] = {}
    with contextlib.redirect_stdout(io.StringIO()):
        for name, step in pipeline_steps(priors):
            before = _snapshot(state)
            step.inject(ctx)
            step.run(catalog, state)
            result[name] = (before, _snapshot(state))
    return PipelineRun(catalog, state, ctx, result)


@pytest.fixture(scope="module")
def transitions(pipeline_run: PipelineRun) -> dict[str, tuple[Snapshot, Snapshot]]:
    return pipeline_run.transitions


def test_terrain_gen_writes_terrain(
    transitions: dict[str, tuple[Snapshot, Snapshot]],
) -> None:
    before, after = transitions["terrain_gen"]
    assert before.terrain == 0
    assert after.terrain > 0


def test_terrain_gen_provides_segmentation(pipeline_run: PipelineRun) -> None:
    zones = pipeline_run.ctx.require(Segmentation).zones
    assert all(zones[level] for level in pipeline_run.state.terrain)


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


@pytest.mark.parametrize("name", ["vegetation", "gameplay", "loot", "scatter"])
def test_placement_steps_change_objs(
    transitions: dict[str, tuple[Snapshot, Snapshot]], name: str
) -> None:
    before, after = transitions[name]
    assert after.objs != before.objs


def test_no_object_stands_on_a_disallowed_terrain(pipeline_run: PipelineRun) -> None:
    catalog = pipeline_run.catalog
    violations = [
        (o.kind, (tx, ty))
        for o in pipeline_run.state.objs
        if o.kind and (grid := pipeline_run.state.terrain.get(o.level)) is not None
        for tx, ty, _blocking in anchored_cells(o.footprint.solid(), o.x, o.y)
        if 0 <= ty < len(grid)
        and 0 <= tx < len(grid[ty])
        and not catalog.allowed_on(o.kind, grid[ty][tx])
    ]
    assert violations == []


def test_no_guard_stands_on_a_mine_visit_tile(pipeline_run: PipelineRun) -> None:
    visit = {
        (o.level, tile)
        for o in pipeline_run.state.objs
        if o.purpose == Purpose.MINE
        for tile in interactive_cells(o.footprint, o.x, o.y)
    }
    guards = [
        o
        for o in pipeline_run.state.objs
        if o.purpose == Purpose.GUARD and (o.level, (o.x, o.y)) in visit
    ]
    assert guards == []


def test_scatter_piles_stay_out_of_every_guard_zone(pipeline_run: PipelineRun) -> None:
    for level in (0, 1):
        level_objs = [o for o in pipeline_run.state.objs if o.level == level]
        zoc = guard_zoc(level_objs)
        piles = [o for o in level_objs if o.purpose == Purpose.RESOURCE_PILE and not o.cache]
        assert piles
        for o in piles:
            for cell in interactive_cells(o.footprint, o.x, o.y):
                assert cell not in zoc, f"pile at {cell} sits in a guard's zone of control"


@pytest.mark.parametrize("name", STEP_NAMES)
def test_every_step_keeps_the_objects_before_it(
    transitions: dict[str, tuple[Snapshot, Snapshot]], name: str
) -> None:
    before, after = transitions[name]
    assert after.objs[: len(before.objs)] == before.objs


def test_a_loot_guard_keeps_its_distance_from_every_other_guard(
    pipeline_run: PipelineRun,
) -> None:
    guards = [o for o in pipeline_run.state.objs if o.purpose == Purpose.GUARD]
    for g in (o for o in pipeline_run.added_by("loot") if o.purpose == Purpose.GUARD):
        others = [(o.x, o.y) for o in guards if o is not g and o.level == g.level]
        assert guard_spaced((g.x, g.y), others), f"loot guard at {(g.x, g.y)} crowds another"


def _touches(o: PlacedObject, blocking: set[tuple[int, Tile]]) -> bool:
    return any(
        (o.level, (x + dx, y + dy)) in blocking
        for x, y, _b in anchored_cells(o.footprint, o.x, o.y)
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
    )


def test_gameplay_objects_sit_next_to_vegetation(pipeline_run: PipelineRun) -> None:
    blocking = {
        (o.level, (x, y))
        for o in pipeline_run.added_by("vegetation")
        for x, y, blk in anchored_cells(o.footprint, o.x, o.y)
        if blk
    }
    placed = [o for o in pipeline_run.added_by("gameplay") if o.purpose != Purpose.GUARD]
    assert placed
    share = sum(_touches(o, blocking) for o in placed) / len(placed)
    assert share >= VEGETATION_TOUCH_FLOOR, f"only {share:.0%} of gameplay objects touch vegetation"

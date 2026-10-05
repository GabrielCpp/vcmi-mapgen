"""RoadsStep run after a whole places pipeline: the roads join every player town, keep to
walkable tiles and cross no closed border."""

import contextlib
import io
from dataclasses import dataclass

import pytest

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.core.planning.content import HopContent
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.reading.borders import AdjacencyKind
from vcmi_mapgen.core.reading.ground import read_ground
from vcmi_mapgen.core.reading.roads import crossed_pairs
from vcmi_mapgen.core.steps import (
    GameplayStep,
    GatedStep,
    LootStep,
    PortalStep,
    RoadsStep,
    ScatterStep,
    TerrainStep,
    TreasureStep,
    VegetationStep,
)
from vcmi_mapgen.core.steps.roads.network import PassageRoads
from vcmi_mapgen.core.steps.roads.sites import homes_of
from vcmi_mapgen.core.steps.terrain_gen.coastline import NoiseForm
from vcmi_mapgen.core.steps.terrain_gen.model import TerrainOptions
from vcmi_mapgen.core.steps.terrain_gen.places import PlacesTerrain
from vcmi_mapgen.core.steps.terrain_gen.result import LevelPlaces, PlaceMap
from vcmi_mapgen.core.steps.vegetation.field.sampler import FieldSampler

SIZE = 48
SEED = 3
PLAYERS = 2


@dataclass(frozen=True, slots=True)
class RoadRun:
    catalog: Catalog
    state: MapState
    places: LevelPlaces
    objs_before: int


def _steps(priors: Priors) -> list[PipelineStep]:
    return [
        TerrainStep(
            priors, PlacesTerrain(NoiseForm()), SEED, TerrainOptions(SIZE, "normal", False, PLAYERS)
        ),
        VegetationStep(priors, FieldSampler(), SEED, PLAYERS, HopContent()),
        GameplayStep(priors, SEED, PLAYERS, SIZE, False),
        GatedStep(priors, SEED, SIZE),
        TreasureStep(priors, SEED, SIZE),
        PortalStep(priors, SEED, SIZE),
        LootStep(priors, SEED, SIZE),
        ScatterStep(priors, SEED, SIZE),
    ]


@pytest.fixture(scope="module")
def road_run(catalog: Catalog, priors: Priors) -> RoadRun:
    state = MapState(size=SIZE)
    ctx = ProviderRegistry()
    with contextlib.redirect_stdout(io.StringIO()):
        for step in _steps(priors):
            step.inject(ctx)
            step.run(catalog, state)
        before = len(state.objs)
        roads = RoadsStep(priors, PassageRoads(), SEED)
        roads.inject(ctx)
        roads.run(catalog, state)
    return RoadRun(catalog, state, ctx.require(PlaceMap).levels[0], before)


def test_roads_step_writes_roads_and_places_no_object(road_run: RoadRun) -> None:
    assert road_run.state.roads[0]
    assert len(road_run.state.objs) == road_run.objs_before


def test_every_road_tile_stays_walkable(road_run: RoadRun) -> None:
    ground = read_ground(road_run.catalog, road_run.state, 0)
    assert ground is not None
    assert set(road_run.state.roads[0]) <= ground.walk


def test_every_player_town_has_a_road(road_run: RoadRun) -> None:
    ground = read_ground(road_run.catalog, road_run.state, 0)
    assert ground is not None
    homes = homes_of(road_run.state.player_towns, 0, road_run.places.label, ground.walk)
    assert len(homes) == PLAYERS
    assert all(t in road_run.state.roads[0] for _, t in homes)


def test_no_road_crosses_a_closed_border(road_run: RoadRun) -> None:
    kinds = road_run.places.kinds
    crossed = crossed_pairs(road_run.places.label, road_run.state.roads[0])
    assert crossed
    assert all(kinds.get(pq, AdjacencyKind.CLOSED) != AdjacencyKind.CLOSED for pq in crossed)

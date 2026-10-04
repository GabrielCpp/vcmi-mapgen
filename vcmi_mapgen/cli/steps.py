from dataclasses import dataclass

from vcmi_mapgen.core.pipeline import PipelineStep
from vcmi_mapgen.core.planning.content import ContentPlanner, HopContent, NoContent
from vcmi_mapgen.core.priors.bundle import Priors
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
from vcmi_mapgen.core.steps.roads.layer import NoRoads, RoadLayer
from vcmi_mapgen.core.steps.roads.network import PassageRoads
from vcmi_mapgen.core.steps.terrain_gen.markov import MarkovTerrain
from vcmi_mapgen.core.steps.terrain_gen.model import TerrainModel, TerrainOptions
from vcmi_mapgen.core.steps.terrain_gen.places import PlacesTerrain
from vcmi_mapgen.core.steps.vegetation.field.sampler import FieldSampler
from vcmi_mapgen.core.steps.vegetation.gibbs.sampler import GibbsSampler
from vcmi_mapgen.core.steps.vegetation.sampler import Sampler

GENERATE_STOP_POINTS = (
    "terrain",
    "vegetation",
    "gameplay",
    "gated",
    "treasure",
    "portal",
    "loot",
    "scatter",
    "roads",
)

SAMPLERS: dict[str, Sampler] = {
    "gibbs": GibbsSampler(),
    "field": FieldSampler(),
}
DEFAULT_VEGETATION = "field"

TERRAIN_MODELS: dict[str, TerrainModel] = {
    "markov": MarkovTerrain(),
    "places": PlacesTerrain(),
}
DEFAULT_TERRAIN = "places"

CONTENTS: dict[str, ContentPlanner] = {
    "markov": NoContent(),
    "places": HopContent(),
}

ROADS: dict[str, RoadLayer] = {
    "markov": NoRoads(),
    "places": PassageRoads(),
}


@dataclass(frozen=True, slots=True)
class StepConfig:
    """What one generation asks for: the seed, the map side, the player count, the water
    mode, whether the map has an underground level, which SAMPLERS entry grows the
    vegetation and which TERRAIN_MODELS entry draws the terrain."""

    seed: int
    size: int
    players: int = 2
    water_mode: str = "normal"
    subterrain: bool = False
    vegetation: str = DEFAULT_VEGETATION
    terrain: str = DEFAULT_TERRAIN


def build_steps(priors: Priors, config: StepConfig) -> list[tuple[str, PipelineStep]]:
    """(name, step) pairs in run order, each step holding the corpus `priors` it reads. The
    terrain model picks the CONTENTS planner and the ROADS layer, so only the places terrain
    plans content and lays roads.
    `name` matches GENERATE_STOP_POINTS so the CLI can truncate the list at the requested
    --stop-after point; Pipeline itself has no concept of a stop point."""
    seed, size, players, subterrain = config.seed, config.size, config.players, config.subterrain
    terrain = TerrainOptions(size, config.water_mode, subterrain, players)
    sampler, content = SAMPLERS[config.vegetation], CONTENTS[config.terrain]
    return [
        ("terrain", TerrainStep(priors, TERRAIN_MODELS[config.terrain], seed, terrain)),
        ("vegetation", VegetationStep(priors, sampler, seed, players, content)),
        ("gameplay", GameplayStep(priors, seed, players, size, subterrain)),
        ("gated", GatedStep(priors, seed, size)),
        ("treasure", TreasureStep(priors, seed, size)),
        ("portal", PortalStep(priors, seed, size)),
        ("loot", LootStep(priors, seed, size)),
        ("scatter", ScatterStep(priors, seed, size)),
        ("roads", RoadsStep(priors, ROADS[config.terrain], seed)),
    ]

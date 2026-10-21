from dataclasses import dataclass

from vcmi_mapgen.core.pipeline import PipelineStep
from vcmi_mapgen.core.planning.content import HopContent
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.steps import (
    CompensationStep,
    DoorsStep,
    GameplayStep,
    GatedStep,
    LootStep,
    PortalStep,
    RemoteStep,
    RoadsStep,
    ScatterStep,
    SetsStep,
    TerrainStep,
    TreasureStep,
    VegetationStep,
)
from vcmi_mapgen.core.steps.roads.network import PassageRoads
from vcmi_mapgen.core.steps.terrain_gen.coastline import NoiseForm, SurfaceForm
from vcmi_mapgen.core.steps.terrain_gen.model import TerrainOptions, TerritoryFront
from vcmi_mapgen.core.steps.terrain_gen.places import PlacesTerrain
from vcmi_mapgen.core.steps.terrain_gen.planned import PlannedFront
from vcmi_mapgen.core.steps.terrain_gen.shapes_first import ShapesFirst
from vcmi_mapgen.core.steps.terrain_gen.water import TopologyForm
from vcmi_mapgen.core.steps.vegetation.field.sampler import FieldSampler
from vcmi_mapgen.core.steps.vegetation.gibbs.sampler import GibbsSampler
from vcmi_mapgen.core.steps.vegetation.sampler import Sampler

GENERATE_STOP_POINTS = (
    "terrain",
    "vegetation",
    "doors",
    "gameplay",
    "gated",
    "treasure",
    "portal",
    "loot",
    "sets",
    "scatter",
    "remote",
    "compensation",
    "roads",
)

SAMPLERS: dict[str, Sampler] = {
    "gibbs": GibbsSampler(),
    "field": FieldSampler(),
}
DEFAULT_VEGETATION = "field"

SURFACE_FORMS: dict[str, SurfaceForm] = {
    "none": NoiseForm(),
    "normal": NoiseForm(),
    "islands": NoiseForm(),
    "topology": TopologyForm(),
}
DEFAULT_WATER = "topology"

FRONTS: dict[str, TerritoryFront] = {
    "shapes": ShapesFirst(),
    "planned": PlannedFront(),
}
DEFAULT_FRONT = "shapes"
COASTS: dict[str, float] = {"shapes": 0.0, "planned": 4.0}


@dataclass(frozen=True, slots=True)
class StepConfig:
    """What one generation asks for: the seed, the map side, the player count, the
    SURFACE_FORMS entry that draws the water, whether the map has an underground level,
    which SAMPLERS entry grows the vegetation, which FRONTS entry draws the surface
    territories, and the team of each player, empty when every player plays alone."""

    seed: int
    size: int
    players: int = 2
    water_mode: str = DEFAULT_WATER
    subterrain: bool = False
    vegetation: str = DEFAULT_VEGETATION
    density: float = 1.0
    teams: tuple[int, ...] = ()
    front: str = DEFAULT_FRONT


def build_steps(priors: Priors, config: StepConfig) -> list[tuple[str, PipelineStep]]:
    """(name, step) pairs in run order, each step holding the corpus `priors` it reads.
    `name` matches GENERATE_STOP_POINTS so the CLI can truncate the list at the requested
    --stop-after point; Pipeline itself has no concept of a stop point."""
    seed, size, players, subterrain = config.seed, config.size, config.players, config.subterrain
    terrain = TerrainOptions(size, config.water_mode, subterrain, players)
    sampler = SAMPLERS[config.vegetation]
    form = (
        TopologyForm(COASTS[config.front])
        if config.water_mode == "topology"
        else SURFACE_FORMS[config.water_mode]
    )
    model = PlacesTerrain(form, FRONTS[config.front])
    gameplay = GameplayStep(priors, seed, players, subterrain, config.density)
    return [
        ("terrain", TerrainStep(priors, model, seed, terrain)),
        ("vegetation", VegetationStep(priors, sampler, seed, players, HopContent())),
        ("doors", DoorsStep(priors, seed, config.teams)),
        ("gameplay", gameplay),
        ("gated", GatedStep(priors, seed, size)),
        ("treasure", TreasureStep(priors, seed, size)),
        ("portal", PortalStep(priors, seed, size)),
        ("loot", LootStep(priors, seed, size)),
        ("sets", SetsStep(priors, seed, size)),
        ("scatter", ScatterStep(priors, seed, size)),
        ("remote", RemoteStep(priors, seed, size)),
        ("compensation", CompensationStep(priors)),
        ("roads", RoadsStep(priors, PassageRoads(), seed)),
    ]

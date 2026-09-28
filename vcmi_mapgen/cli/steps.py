from dataclasses import dataclass

from vcmi_mapgen.core.pipeline import PipelineStep
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.steps import (
    BorderStep,
    GameplayStep,
    GatedStep,
    LootStep,
    PortalStep,
    ScatterStep,
    TerrainStep,
    TreasureStep,
    VegetationStep,
)

GENERATE_STOP_POINTS = (
    "terrain",
    "vegetation",
    "gameplay",
    "gated",
    "treasure",
    "border",
    "portal",
    "loot",
    "scatter",
)


@dataclass(frozen=True, slots=True)
class StepConfig:
    """What one generation asks for: the seed, the map side, the player count, the water
    mode and whether the map has an underground level."""

    seed: int
    size: int
    players: int = 2
    water_mode: str = "normal"
    subterrain: bool = False


def build_steps(priors: Priors, config: StepConfig) -> list[tuple[str, PipelineStep]]:
    """(name, step) pairs in run order, each step holding the corpus `priors` it reads.
    `name` matches GENERATE_STOP_POINTS so the CLI can truncate the list at the requested
    --stop-after point; Pipeline itself has no concept of a stop point."""
    seed, size, players, subterrain = config.seed, config.size, config.players, config.subterrain
    return [
        ("terrain", TerrainStep(priors, size, seed, config.water_mode, subterrain)),
        ("vegetation", VegetationStep(priors, seed, players)),
        ("gameplay", GameplayStep(priors, seed, players, size, subterrain)),
        ("gated", GatedStep(priors, seed, size)),
        ("treasure", TreasureStep(priors, seed, size)),
        ("border", BorderStep(seed, size)),
        ("portal", PortalStep(priors, seed, size)),
        ("loot", LootStep(priors, seed, size)),
        ("scatter", ScatterStep(priors, seed, size)),
    ]

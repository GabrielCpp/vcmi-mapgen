from vcmi_mapgen.core.pipeline import PipelineStep
from vcmi_mapgen.core.steps import (
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

GENERATE_STOP_POINTS = (
    "terrain",
    "segment",
    "vegetation",
    "gameplay",
    "gated",
    "treasure",
    "border",
    "portal",
    "loot",
    "scatter",
)


def build_steps(
    seed: int, size: int, players: int, water_mode: str, subterrain: bool
) -> list[tuple[str, PipelineStep]]:
    """(name, step) pairs in run order. `name` matches GENERATE_STOP_POINTS so the CLI
    can truncate the list at the requested --stop-after point; Pipeline itself has no
    concept of a stop point."""
    steps: list[tuple[str, PipelineStep]] = [
        (
            "terrain",
            TerrainStep(size=size, seed=seed, water_mode=water_mode, subterrain=subterrain),
        ),
        ("segment", SegmentStep()),
    ]
    steps.append(("vegetation", VegetationStep(seed=seed, players=players)))
    steps.append(
        (
            "gameplay",
            GameplayStep(seed=seed, players=players, size=size, subterrain=subterrain),
        )
    )
    steps.append(("gated", GatedStep(seed=seed, size=size)))
    steps.append(("treasure", TreasureStep(seed=seed, size=size)))
    steps.append(("border", BorderStep(seed=seed, size=size)))
    steps.append(("portal", PortalStep(seed=seed, size=size)))
    steps.append(("loot", LootStep(seed=seed, size=size)))
    steps.append(("scatter", ScatterStep(seed=seed, size=size)))
    return steps

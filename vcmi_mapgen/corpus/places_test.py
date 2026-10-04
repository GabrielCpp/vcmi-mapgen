from pathlib import Path

from vcmi_mapgen.core.priors.places import (
    PaletteCount,
    PlaceContent,
    PlaceCount,
    PlaceStats,
    RoadCount,
    RoadStats,
)
from vcmi_mapgen.corpus.places import load_places, save_places


def _stats() -> PlaceStats:
    return PlaceStats(
        counts=(PlaceCount(5, 2, 900), PlaceCount(3, 4, 400)),
        rel_size={"home": (0.25, 0.3125), "pocket": (0.0125,)},
        adjacency={"home|middle|gated": 3},
        degree={"home": (2, 3)},
        home_separation=(0.875,),
        compactness={"home": (0.5,)},
        roughness={"home": (1.25,)},
        dominant={"home": {2: 4, 7: 1}},
        dominant_share={"home": (0.75,)},
        border_kinds={"gated|same|barrier": 2},
        barrier_depth=(1.5, 2.0),
        palette_counts=(PaletteCount(3, 5, 900), PaletteCount(1, 3, 400)),
        same_by_roles={"home|middle": (2, 5)},
        content=(
            PlaceContent("home", 0, 400, 3, 9000, (1, 2), 1),
            PlaceContent("pocket", -1, 30, 1, 2000),
        ),
        roads=RoadStats(
            counts=(RoadCount(40, 900, 3, 2, 1, 2, 2),),
            crossed={"home|middle|gated": (1, 2)},
            surface={0: {1: 30}, -1: {2: 10}},
            on_dominant=(35, 40),
            land_dominant=(600, 900),
            near=(4, 9),
        ),
    )


def test_place_stats_survive_a_save_and_load_per_level(tmp_path: Path) -> None:
    surface = _stats()
    underground = PlaceStats(counts=(PlaceCount(1, 2, 50),))
    save_places(tmp_path, 0, surface)
    save_places(tmp_path, 1, underground)
    assert load_places(tmp_path, 0) == surface
    assert load_places(tmp_path, 1) == underground

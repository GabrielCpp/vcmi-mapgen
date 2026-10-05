from pathlib import Path

from vcmi_mapgen.core.priors.water import WaterPriors, WaterTarget
from vcmi_mapgen.corpus.water import load_water, save_water


def test_saved_water_priors_load_back_unchanged(tmp_path: Path) -> None:
    priors = WaterPriors(
        beta=(-1.5, 0.25, 2.0),
        static_beta=(-1.0, 0.5),
        targets=(WaterTarget(0.25, 0.5, 2), WaterTarget(0.0, 0.0, 1)),
    )
    save_water(tmp_path, priors)
    assert load_water(tmp_path) == priors

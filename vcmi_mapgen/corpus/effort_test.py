from pathlib import Path

from vcmi_mapgen.core.priors.effort import EffortPriors, RewardTier
from vcmi_mapgen.corpus.effort import load_effort, save_effort, tuned_effort


def test_saved_effort_priors_load_back_unchanged(tmp_path: Path) -> None:
    priors = EffortPriors(
        toll=(0, 1, 2, 3, 4, 5, 6, 7),
        edges=(5, 9, 30),
        baskets=({"treasure": 1}, {"minor": 2}, {"major": 3}, {"relic": 4}),
        grants=(RewardTier((1, 2, 3), (100,), (200, 300), (1, 2), (1,)),) * 4,
        boxes=(0, 1, 2, 3),
        medians={"treasure": 4.0, "relic": 40.0},
        counts={"treasure": 10, "relic": 2},
    )
    save_effort(tmp_path, priors)
    assert load_effort(tmp_path) == priors


def test_tuned_effort_falls_back_to_the_defaults_without_a_file(tmp_path: Path) -> None:
    assert tuned_effort(tmp_path) == EffortPriors()

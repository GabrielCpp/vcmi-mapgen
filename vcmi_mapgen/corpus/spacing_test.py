from pathlib import Path

from vcmi_mapgen.core.priors.spacing import SpacingFit, SpacingPriors
from vcmi_mapgen.corpus.spacing import load_spacing, save_spacing


def test_saved_spacing_loads_back_unchanged(tmp_path: Path) -> None:
    kde = SpacingFit("kde", (0.2,), 40, 0.1, 0.8, 2.1, 12.5, 0.004, (0.1, 0.5, 1.0))
    expo = SpacingFit("exponential", (1.1,), 90, 0.1, 0.7, 2.5, 80.0, 0.4)
    priors = SpacingPriors({"windmill:": kde}, {"MANA": expo})
    save_spacing(tmp_path, priors)
    assert load_spacing(tmp_path) == priors


def test_no_spacing_file_leaves_every_kind_unfitted(tmp_path: Path) -> None:
    assert load_spacing(tmp_path) == SpacingPriors()

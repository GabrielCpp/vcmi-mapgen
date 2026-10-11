from pathlib import Path

from vcmi_mapgen.core.priors.counts import CountCurve, FamilyCurves, FamilyFit
from vcmi_mapgen.corpus.counts import load_families, save_families


def test_saved_family_curves_load_back_unchanged(tmp_path: Path) -> None:
    curves = FamilyCurves(
        2500,
        {
            "BANK": FamilyFit(CountCurve(-3.5, 1.0, 0.2), 0.07),
            "DWELLING:4": FamilyFit(CountCurve(-8.0, 1.27, -0.3), 0.46),
        },
    )
    save_families(tmp_path, curves)
    assert load_families(tmp_path) == curves


def test_no_family_file_leaves_every_family_unfitted(tmp_path: Path) -> None:
    assert load_families(tmp_path) == FamilyCurves()

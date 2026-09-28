"""Reliability tests for loading the mined vegetation statistics."""

from pathlib import Path

import pytest

from vcmi_mapgen.conftest import vegetation_mined
from vcmi_mapgen.corpus.vegetation import load_vegetation


@pytest.mark.skipif(not vegetation_mined(), reason="data/pp stats not mined")
def test_load_vegetation_reads_one_terrain(pp_dir: Path) -> None:
    st = load_vegetation(pp_dir, "grass")
    assert st.terrain == "grass"
    assert set(st.lam) == set(st.anch)
    assert st.cell is not None
    assert 0 < st.veg_blocked_frac < 1

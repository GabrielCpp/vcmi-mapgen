"""Reliability tests for loading the mined vegetation statistics."""

import os

import pytest

from vcmi_mapgen.corpus.vegetation import PP_DIR, load_vegetation

HAVE_STATS = os.path.exists(os.path.join(PP_DIR, "veg_grass.json"))


@pytest.mark.skipif(not HAVE_STATS, reason="data/pp stats not mined")
def test_load_vegetation_reads_one_terrain() -> None:
    st = load_vegetation("grass")
    assert st.terrain == "grass"
    assert set(st.lam) == set(st.anch)
    assert st.cell is not None
    assert 0 < st.veg_blocked_frac < 1

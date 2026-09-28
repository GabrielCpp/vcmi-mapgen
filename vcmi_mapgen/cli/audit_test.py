"""Reliability tests for the corpus variety audit."""

import os

import pytest

from vcmi_mapgen.cli.audit import audit_variety
from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.corpus.gameplay import STATS_PATH
from vcmi_mapgen.corpus.vegetation import PP_DIR

HAVE_STATS = os.path.exists(os.path.join(PP_DIR, "veg_grass.json"))
needs_stats = pytest.mark.skipif(not HAVE_STATS, reason="data/pp stats not mined")


@needs_stats
def test_audit_variety_green(catalog: Catalog) -> None:
    """Every corpus (purpose, animation) on land must be reachable through the generator
    (identity via the catalog, placement via a pool) — the acceptance check for corpus
    visitable variety."""

    if not os.path.exists(STATS_PATH):
        pytest.skip("gameplay stats not mined")
    gaps = audit_variety(catalog)
    assert gaps == [], f"variety gaps: {gaps}"

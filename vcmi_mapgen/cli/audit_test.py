"""Reliability tests for the corpus variety audit."""

import pytest

from vcmi_mapgen.cli.audit import audit_variety
from vcmi_mapgen.cli.settings import Settings
from vcmi_mapgen.conftest import gameplay_mined, vegetation_mined
from vcmi_mapgen.core.catalog import Catalog

needs_stats = pytest.mark.skipif(not vegetation_mined(), reason="data/pp stats not mined")


@needs_stats
def test_audit_variety_green(catalog: Catalog, settings: Settings) -> None:
    """Every corpus (purpose, animation) on land must be reachable through the generator
    (identity via the catalog, placement via a pool) — the acceptance check for corpus
    visitable variety."""

    if not gameplay_mined():
        pytest.skip("gameplay stats not mined")
    gaps = audit_variety(catalog, settings.pp_dir)
    assert gaps == [], f"variety gaps: {gaps}"

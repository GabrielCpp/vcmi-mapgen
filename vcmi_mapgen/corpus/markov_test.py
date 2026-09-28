"""Loading the terrain Markov tables."""

from pathlib import Path

import pytest

from vcmi_mapgen.corpus.markov import load_tables
from vcmi_mapgen.kit import pp_cache


def test_missing_tables_name_mine_stats(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pp_cache, "PP_DIR", tmp_path)
    load_tables.cache_clear()
    with pytest.raises(pp_cache.MissingCacheError, match="mine-stats"):
        _ = load_tables(0)
    load_tables.cache_clear()

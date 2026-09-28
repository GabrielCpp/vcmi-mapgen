"""Loading the terrain Markov tables."""

from pathlib import Path

import pytest

from vcmi_mapgen.corpus import cache
from vcmi_mapgen.corpus.markov import load_tables


def test_missing_tables_name_mine_stats(tmp_path: Path) -> None:
    with pytest.raises(cache.MissingCacheError, match="mine-stats"):
        _ = load_tables(tmp_path, 0)

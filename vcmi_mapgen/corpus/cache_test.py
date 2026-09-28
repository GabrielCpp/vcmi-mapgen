from pathlib import Path

import pytest

from vcmi_mapgen.corpus import cache


def test_missing_cache_names_mine_stats(tmp_path: Path) -> None:
    with pytest.raises(cache.MissingCacheError, match="mine-stats"):
        _ = cache.read(tmp_path / "absent.json")


def test_wrong_version_names_mine_stats(tmp_path: Path) -> None:
    path = tmp_path / "stats.json"
    cache.write(path, "builder", {"_version": 1})
    with pytest.raises(cache.MissingCacheError, match="mine-stats"):
        _ = cache.read(path, version=2)


def test_write_records_source(tmp_path: Path) -> None:
    path = tmp_path / "stats.json"
    cache.write(path, "builder", {"_version": 2, "n": 3})
    assert cache.read(path, version=2) == {"_source": "builder", "_version": 2, "n": 3}

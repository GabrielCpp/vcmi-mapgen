from pathlib import Path

import pytest

from vcmi_mapgen.kit import pp_cache


def test_missing_cache_names_mine_stats(tmp_path: Path) -> None:
    with pytest.raises(pp_cache.MissingCacheError, match="mine-stats"):
        _ = pp_cache.read(tmp_path / "absent.json")


def test_wrong_version_names_mine_stats(tmp_path: Path) -> None:
    path = tmp_path / "stats.json"
    pp_cache.write(path, "builder", {"_version": 1})
    with pytest.raises(pp_cache.MissingCacheError, match="mine-stats"):
        _ = pp_cache.read(path, version=2)


def test_write_records_source(tmp_path: Path) -> None:
    path = tmp_path / "stats.json"
    pp_cache.write(path, "builder", {"_version": 2, "n": 3})
    assert pp_cache.read(path, version=2) == {"_source": "builder", "_version": 2, "n": 3}

import os
from pathlib import Path

import pytest

from vcmi_mapgen.corpus.maps import all_map_names


def test_all_map_names_is_independent_of_listdir_order(
    monkeypatch: pytest.MonkeyPatch, maps_dir: Path
) -> None:
    real_listdir = os.listdir
    names = all_map_names(maps_dir)

    def reversed_listdir(path: str) -> list[str]:
        return list(reversed(real_listdir(path)))

    monkeypatch.setattr(os, "listdir", reversed_listdir)
    assert all_map_names(maps_dir) == names

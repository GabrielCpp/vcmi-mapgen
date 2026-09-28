from pathlib import Path

import pytest

from vcmi_mapgen.vcmi.install import InstallNotFoundError, find_install


def test_vcmi_home_wins(tmp_path: Path) -> None:
    install = find_install({"VCMI_HOME": str(tmp_path), "HOME": "/nonexistent"}, "linux")
    assert install.home == tmp_path
    assert install.data_dir == tmp_path / "Data"


def test_vcmi_home_expands_tilde(tmp_path: Path) -> None:
    (tmp_path / "vcmi").mkdir()
    install = find_install({"VCMI_HOME": "~/vcmi", "HOME": str(tmp_path)}, "linux")
    assert install.home == tmp_path / "vcmi"


def test_missing_vcmi_home_raises_naming_it() -> None:
    with pytest.raises(InstallNotFoundError, match="VCMI_HOME"):
        _ = find_install({"VCMI_HOME": "/nonexistent/vcmi", "HOME": "/nonexistent"}, "linux")


def test_linux_xdg_candidate(tmp_path: Path) -> None:
    (tmp_path / "share" / "vcmi").mkdir(parents=True)
    env = {"HOME": "/nonexistent", "XDG_DATA_HOME": str(tmp_path / "share")}
    assert find_install(env, "linux").home == tmp_path / "share" / "vcmi"


def test_darwin_candidate(tmp_path: Path) -> None:
    home = tmp_path / "Library" / "Application Support" / "vcmi"
    home.mkdir(parents=True)
    assert find_install({"HOME": str(tmp_path)}, "darwin").home == home


def test_win32_uses_userprofile(tmp_path: Path) -> None:
    home = tmp_path / "Documents" / "My Games" / "vcmi"
    home.mkdir(parents=True)
    assert find_install({"USERPROFILE": str(tmp_path)}, "win32").home == home


def test_no_candidate_raises() -> None:
    with pytest.raises(InstallNotFoundError, match="VCMI_HOME"):
        _ = find_install({"HOME": "/nonexistent"}, "linux")

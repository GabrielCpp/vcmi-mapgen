import json
from pathlib import Path

import pytest

from vcmi_mapgen.vcmi.content.enabled import (
    ContentConflictError,
    ContentSetting,
    UnknownModError,
    enable,
)
from vcmi_mapgen.vcmi.content.manifest import read_manifests


def _mod(folder: Path, **doc: object) -> None:
    folder.mkdir(parents=True)
    _ = (folder / "mod.json").write_text("// manifest\n" + json.dumps(doc) + "\n")


@pytest.fixture
def mods(tmp_path: Path) -> Path:
    _mod(tmp_path / "Base", depends=["vcmi"])
    _mod(tmp_path / "Base" / "Mods" / "Towns")
    _mod(tmp_path / "Base" / "mods" / "Portraits", keepDisabled=True)
    _mod(tmp_path / "Base" / "Mods" / "Patch", depends=["other"])
    _mod(tmp_path / "Other", depends=["base.towns"])
    _mod(tmp_path / "Rival", conflicts=["base"])
    return tmp_path


def test_a_submod_takes_its_parent_id_and_depends_on_it(mods: Path) -> None:
    manifests = read_manifests(mods)
    assert manifests["base.towns"].depends == {"base"}
    assert manifests["base"].submods == ("base.patch", "base.towns", "base.portraits")


def test_a_mod_pulls_in_its_dependencies_and_submods(mods: Path) -> None:
    manifests = read_manifests(mods)
    assert enable(ContentSetting(frozenset({"Base"})), manifests).mods == {"base", "base.towns"}
    assert enable(ContentSetting(frozenset({"other"})), manifests).mods == {
        "base",
        "base.towns",
        "base.patch",
        "other",
    }


def test_a_kept_disabled_submod_joins_only_when_named(mods: Path) -> None:
    named = enable(ContentSetting(frozenset({"base.portraits"})), read_manifests(mods))
    assert "base.portraits" in named.mods


def test_a_conflict_or_a_missing_mod_stops_generation(mods: Path) -> None:
    manifests = read_manifests(mods)
    with pytest.raises(ContentConflictError, match="rival"):
        _ = enable(ContentSetting(frozenset({"base", "rival"})), manifests)
    with pytest.raises(UnknownModError, match="nowhere"):
        _ = enable(ContentSetting(frozenset({"nowhere"})), manifests)


def test_a_banned_name_is_never_allowed() -> None:
    enabled = enable(ContentSetting(banned=frozenset({"pandoraBox"})), {})
    assert not enabled.allows("pandora", "pandoraBox")
    assert enabled.allows("pandora", None)

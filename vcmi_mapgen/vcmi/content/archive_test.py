import zipfile
from pathlib import Path

from vcmi_mapgen.vcmi.content.archive import EmptyArchive, open_archive


def test_a_folder_mod_reads_its_content_without_regard_to_case(tmp_path: Path) -> None:
    sprite = tmp_path / "Content" / "Sprites" / "a.def"
    sprite.parent.mkdir(parents=True)
    _ = sprite.write_bytes(b"def")
    archive = open_archive(tmp_path)
    assert archive.read("sprites/A.DEF") == b"def"
    assert archive.read("sprites/b.def") is None


def test_a_zipped_mod_reads_the_same_way(tmp_path: Path) -> None:
    with zipfile.ZipFile(tmp_path / "content.zip", "w") as z:
        z.writestr("config/Objects.json", "{}")
    archive = open_archive(tmp_path)
    assert archive.read("CONFIG/objects.json") == b"{}"
    assert archive.read("config/") is None


def test_a_mod_with_no_content_reads_nothing(tmp_path: Path) -> None:
    assert isinstance(open_archive(tmp_path), EmptyArchive)

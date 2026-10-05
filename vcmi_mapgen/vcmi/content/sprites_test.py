from pathlib import Path

from vcmi_mapgen.vcmi.content.archive import EmptyArchive, FolderArchive
from vcmi_mapgen.vcmi.content.sprites import SpriteSource


def _archive(root: Path, files: dict[str, bytes]) -> FolderArchive:
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_bytes(data)
    return FolderArchive(root)


def test_a_sprite_comes_from_the_base_game_first(tmp_path: Path) -> None:
    base = _archive(tmp_path / "base", {"avtgems0.def": b"base"})
    mod = _archive(tmp_path / "mod", {"Sprites/avtgems0.def": b"mod"})
    assert SpriteSource(base, [mod]).read("avtgems0.def") == b"base"


def test_a_mod_sprite_is_read_from_its_sprites_folder(tmp_path: Path) -> None:
    first = _archive(tmp_path / "a", {"Sprites/Other/x.def": b"x"})
    second = _archive(tmp_path / "b", {"Sprites/Fair/Tent.def": b"tent"})
    source = SpriteSource(EmptyArchive(), [first, second])
    assert source.read("fair/tent") == b"tent"
    assert source.read("fair/tent.def") == b"tent"
    assert source.read("fair/none") is None

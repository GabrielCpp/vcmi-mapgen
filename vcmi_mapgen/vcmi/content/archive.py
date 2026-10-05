"""`ContentArchive`: the files one mod ships, read from its content folder or its zip."""

import zipfile
from pathlib import Path
from typing import Protocol, final

CONTENT_DIR = "content"
CONTENT_ZIP = "content.zip"


class ContentArchive(Protocol):
    """One mod's content by path from the content root, matched without regard to case."""

    def read(self, name: str) -> bytes | None: ...


@final
class FolderArchive:
    """A mod whose content lies unpacked in its ``content`` folder."""

    def __init__(self, root: Path) -> None:
        self._files = {
            p.relative_to(root).as_posix().lower(): p for p in root.rglob("*") if p.is_file()
        }

    def read(self, name: str) -> bytes | None:
        path = self._files.get(name.lower())
        return None if path is None else path.read_bytes()


@final
class ZipArchive:
    """A mod whose content ships packed in its ``content.zip``."""

    def __init__(self, path: Path) -> None:
        self._path = path
        with zipfile.ZipFile(path) as z:
            self._names = {n.lower(): n for n in z.namelist() if not n.endswith("/")}

    def read(self, name: str) -> bytes | None:
        real = self._names.get(name.lower())
        if real is None:
            return None
        with zipfile.ZipFile(self._path) as z:
            return z.read(real)


@final
class EmptyArchive:
    """A mod that ships no content of its own."""

    def read(self, name: str) -> bytes | None:
        _ = name
        return None


def _child(folder: Path, name: str) -> Path | None:
    return next((p for p in sorted(folder.iterdir()) if p.name.lower() == name), None)


def open_archive(folder: Path) -> ContentArchive:
    """The archive of the mod in ``folder``: its content folder, else its zip, else none."""
    root = _child(folder, CONTENT_DIR)
    if root is not None and root.is_dir():
        return FolderArchive(root)
    packed = _child(folder, CONTENT_ZIP)
    if packed is not None and packed.is_file():
        return ZipArchive(packed)
    return EmptyArchive()

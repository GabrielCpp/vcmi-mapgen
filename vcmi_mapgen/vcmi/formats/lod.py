import os
import struct
import zlib
from functools import cache
from pathlib import Path
from typing import NamedTuple

LOD_FILES = ["H3sprite.lod", "H3ab_spr.lod", "H3bitmap.lod", "H3ab_bmp.lod"]


class LodEntry(NamedTuple):
    path: str
    offset: int
    size: int
    csize: int


class LodIndex:
    def __init__(self, data_dir: Path) -> None:
        self._files: dict[str, LodEntry] = {}
        for lodname in LOD_FILES:
            path = os.path.join(data_dir, lodname)
            if not os.path.exists(path):
                continue
            with open(path, "rb") as f:
                _ = f.seek(8)
                count = struct.unpack("<I", f.read(4))[0]
                _ = f.seek(92)
                for _i in range(count):
                    raw = f.read(16)
                    name = raw.rstrip(b"\x00").decode("latin1", "replace").lower().split("\x00")[0]
                    off, size, _unused, csize = struct.unpack("<IIII", f.read(16))
                    if name not in self._files:
                        self._files[name] = LodEntry(path, off, size, csize)

    def read(self, name: str) -> bytes | None:
        """Payload of a LOD entry keyed by lowercase name (".def" appended when absent). A
        csize of 0 means the entry is stored uncompressed with `size` bytes. Any other csize
        means zlib data, as in VCMI, even when it equals `size`. A zlib failure means the
        entry is stored uncompressed anyway, so the raw bytes return."""
        key = name.lower()
        if key not in self._files and not key.endswith(".def"):
            key += ".def"
        if key not in self._files:
            return None
        entry = self._files[key]
        nbytes = entry.csize if entry.csize else entry.size
        with open(entry.path, "rb") as f:
            _ = f.seek(entry.offset)
            raw = f.read(nbytes)
        if not entry.csize:
            return raw
        try:
            return zlib.decompress(raw)
        except zlib.error:
            return raw


@cache
def lod(data_dir: Path) -> LodIndex:
    return LodIndex(data_dir)

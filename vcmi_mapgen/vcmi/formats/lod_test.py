import struct
import zlib
from pathlib import Path

from vcmi_mapgen.vcmi.formats.lod import LOD_FILES, LodIndex

HEADER = 92
NAME = 16


def _lod(path: Path, entries: list[tuple[str, bytes, int, int]]) -> None:
    table = b""
    body = b""
    offset = HEADER + len(entries) * 32
    for name, data, size, csize in entries:
        table += name.encode().ljust(NAME, b"\x00")
        table += struct.pack("<IIII", offset + len(body), size, 0, csize)
        body += data
    head = bytearray(HEADER)
    head[8:12] = struct.pack("<I", len(entries))
    _ = path.write_bytes(bytes(head) + table + body)


def test_entries_read_stored_and_compressed(tmp_path: Path) -> None:
    payload = b"C\x00\x00\x00" + bytes(range(40))
    packed = zlib.compress(payload)
    _lod(
        tmp_path / LOD_FILES[0],
        [
            ("stored.def", payload, len(payload), 0),
            ("packed.def", packed, len(payload), len(packed)),
            ("same.def", packed, len(packed), len(packed)),
            ("plain.def", payload, len(payload), len(payload)),
        ],
    )
    index = LodIndex(tmp_path)
    assert index.read("stored") == payload
    assert index.read("PACKED.def") == payload
    assert index.read("same") == payload
    assert index.read("plain") == payload
    assert index.read("absent") is None

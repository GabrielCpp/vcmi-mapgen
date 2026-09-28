"""Tests for the H3 DEF sprite decoder (vcmi/formats/defs.py) across all four frame
formats. A format 3 mistake mangles every mountain, town and monster, so format 3 is
the main thing these tests guard.

They require the local H3 sprite LOD files; the whole module is skipped when those
are absent (e.g. CI without a VCMI install).
"""

import struct

import pytest
from PIL import Image

from vcmi_mapgen.conftest import find_install
from vcmi_mapgen.vcmi.formats.defs import parse_def
from vcmi_mapgen.vcmi.formats.lod import LOD_FILES, LodIndex, lod

_INSTALL = find_install()
DATA_DIR = _INSTALL.data_dir if _INSTALL is not None else None
pytestmark = pytest.mark.skipif(
    DATA_DIR is None or not any((DATA_DIR / f).exists() for f in LOD_FILES),
    reason="H3 sprite LOD files not found (set VCMI_HOME)",
)


def _index() -> LodIndex:
    assert DATA_DIR is not None
    return lod(DATA_DIR)


# One representative DEF per H3 sprite compression format (discovered from the LOD):
#   0 = raw, 1 = per-line RLE, 2 = per-line typed RLE, 3 = per-32px-block typed RLE.
FORMAT_REPRESENTATIVES: dict[int, str] = {
    0: "grastl.def",  # grass terrain tile
    1: "adopb1b.def",  # animated decoration
    2: "dirtrd.def",  # dirt road overlay
    3: "AVLpntr7.def",  # 128x128 mountain (the format the decoder bug mangled)
}


def _first_frame_header(defname: str) -> tuple[int, int, int]:
    """(comp, fullW, fullH) read straight from the DEF's first frame header."""
    data = _index().read(defname)
    assert data and len(data) >= 40, f"{defname}: empty/short DEF"
    pos = 16 + 256 * 3
    _bid, nframes = struct.unpack_from("<II", data, pos)
    pos += 16
    pos += nframes * 13  # frame name table
    offsets: tuple[int, ...] = struct.unpack_from("<" + "I" * nframes, data, pos)
    foff = offsets[0]
    (comp,) = struct.unpack_from("<I", data, foff + 4)
    fullw, fullh = struct.unpack_from("<II", data, foff + 8)
    return comp, fullw, fullh


def _nonempty(img: Image.Image) -> bool:
    """True if any pixel is non-transparent."""
    return img.convert("RGBA").getchannel("A").getbbox() is not None


def _frames(defname: str) -> list[list[Image.Image]] | None:
    data = _index().read(defname.lower())
    return parse_def(data) if data is not None else None


@pytest.mark.parametrize("fmt,defname", sorted(FORMAT_REPRESENTATIVES.items()))
def test_all_four_def_formats_decode(fmt: int, defname: str) -> None:
    """Each of the four H3 sprite formats decodes to a frame of the header's
    declared full size, with real (non-transparent) content."""
    comp, fullw, fullh = _first_frame_header(defname)
    assert comp == fmt, f"{defname}: expected format {fmt}, header says {comp}"

    groups = _frames(defname)
    assert groups and groups[0], f"{defname}: no frames decoded"
    frame0 = groups[0][0]
    assert frame0.size == (fullw, fullh), (
        f"{defname} (format {fmt}): decoded {frame0.size}, header full {fullw}x{fullh}"
    )
    assert _nonempty(frame0), f"{defname} (format {fmt}): decoded frame is fully transparent"


def test_known_object_sprites_decode() -> None:
    """A spot-check of recognizable object sprites (incl. a 128x128 mountain)."""
    known = {
        "AVLpntr7": (128, 128),  # mountain mass
        "AVLman30": (32, 32),  # small decoration
        "AVTrndm0": (64, 32),  # random treasure
    }
    for anim, expect in known.items():
        groups = _frames(anim)
        assert groups and groups[0], f"{anim}: not decoded"
        frame0 = groups[0][0]
        assert frame0.size == expect, f"{anim}: size {frame0.size}, expected {expect}"
        assert _nonempty(frame0), f"{anim}: fully transparent"

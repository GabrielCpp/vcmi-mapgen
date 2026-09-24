"""Reliability tests for the H3-sprite rendering engine (renderers/sprites.py).

These guard the parts that silently broke before: the DEF frame decoder across all
four H3 sprite formats (the format-3 block decoder in particular), terrain-tile
decoding, decode coverage over every sprite the engine actually composites, and
renderer determinism.

They require the local H3 sprite LOD files; the whole module is skipped when those
are absent (e.g. CI without a VCMI install).

Run: `uv run pytest vcmi_mapgen/renderers/sprites_test.py -q`
"""

import os
import struct

import pytest
from PIL import Image

import vcmi_mapgen.kit.objects as OR
import vcmi_mapgen.renderers.sprites as RE
from vcmi_mapgen.kit.lod import LOD_DIR, LOD_FILES, lod
from vcmi_mapgen.models import PlacedObject

TEST_MAP = "All for One"

# Skip the whole module if the H3 sprite LODs are not installed on this machine.
_lod_present = os.path.isdir(LOD_DIR) and any(
    os.path.exists(os.path.join(LOD_DIR, f)) for f in LOD_FILES
)
pytestmark = pytest.mark.skipif(
    not _lod_present, reason=f"H3 sprite LOD files not found in {LOD_DIR}"
)

# One representative DEF per H3 sprite compression format (discovered from the LOD):
#   0 = raw, 1 = per-line RLE, 2 = per-line typed RLE, 3 = per-32px-block typed RLE.
FORMAT_REPRESENTATIVES: dict[int, str] = {
    0: "grastl.def",  # grass terrain tile
    1: "adopb1b.def",  # animated decoration
    2: "dirtrd.def",  # dirt road overlay
    3: "AVLpntr7.def",  # 128x128 mountain (the format the decoder bug mangled)
}


# --------------------------------------------------------------------------- helpers
def _first_frame_header(defname: str) -> tuple[int, int, int]:
    """(comp, fullW, fullH) read straight from the DEF's first frame header."""
    data = lod().read(defname)
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


# --------------------------------------------------------------------------- tests
def test_lod_index_loaded() -> None:
    """The LOD index should expose the thousands of DEFs the renderer relies on."""
    n_defs = lod().def_count()
    assert n_defs > 1000, f"only {n_defs} DEFs indexed — LOD load looks broken"


@pytest.mark.parametrize("fmt,defname", sorted(FORMAT_REPRESENTATIVES.items()))
def test_all_four_def_formats_decode(fmt: int, defname: str) -> None:
    """Each of the four H3 sprite formats decodes to a frame of the header's
    declared full size, with real (non-transparent) content."""
    comp, fullw, fullh = _first_frame_header(defname)
    assert comp == fmt, f"{defname}: expected format {fmt}, header says {comp}"

    groups = RE.get_def(defname)
    assert groups and groups[0], f"{defname}: no frames decoded"
    frame0 = groups[0][0]
    assert frame0.size == (fullw, fullh), (
        f"{defname} (format {fmt}): decoded {frame0.size}, header full {fullw}x{fullh}"
    )
    assert _nonempty(frame0), f"{defname} (format {fmt}): decoded frame is fully transparent"


def test_every_terrain_tile_decodes() -> None:
    """Every terrain .def decodes, and terr_tile_img yields a 32x32 non-empty tile."""
    for tc, defname in RE.TERR_DEF.items():
        groups = RE.get_def(defname)
        assert groups and groups[0], f"terrain {tc} ({defname}) failed to decode"
        tile = RE.terr_tile_img(f"{tc}0_")
        assert tile.size == (RE.TILE, RE.TILE), f"{tc}: tile size {tile.size}"
        assert _nonempty(tile), f"{tc} ({defname}): terrain tile is fully transparent"


def test_known_object_sprites_decode() -> None:
    """A spot-check of recognizable object sprites (incl. a 128x128 mountain)."""
    known = {
        "AVLpntr7": (128, 128),  # mountain mass
        "AVLman30": (32, 32),  # small decoration
        "AVTrndm0": (64, 32),  # random treasure
    }
    for anim, expect in known.items():
        groups = RE.get_def(anim)
        assert groups and groups[0], f"{anim}: not decoded"
        frame0 = groups[0][0]
        assert frame0.size == expect, f"{anim}: size {frame0.size}, expected {expect}"
        assert _nonempty(frame0), f"{anim}: fully transparent"


def test_decode_coverage_over_corpus_sprites() -> None:
    """Reliability sweep: every distinct object sprite the engine would composite for
    the test map must, when present in the LOD, decode to a non-empty frame of the
    header-declared size. Sprites genuinely absent from the LOD are reported, not
    failed (that is a data-availability issue, not a decoder fault)."""
    fm = OR.load_faithful(TEST_MAP)
    anims = sorted({o.animation for o in fm.objects if o.animation})
    assert anims, "no object animations found in the test map"

    absent: list[str] = []
    bad: list[tuple[str, str]] = []
    checked = 0
    for anim in anims:
        data = lod().read(anim)
        if not data or len(data) < 40:  # not in LOD (data availability, not decoder)
            absent.append(anim)
            continue
        checked += 1
        try:
            _comp, fullw, fullh = _first_frame_header(anim)
            groups = RE.get_def(anim)
        except Exception as e:
            bad.append((anim, f"exc:{e}"))
            continue
        if not (groups and groups[0]):
            bad.append((anim, "no frames"))
        elif groups[0][0].size != (fullw, fullh):
            bad.append((anim, f"{groups[0][0].size} != {fullw}x{fullh}"))
        elif not _nonempty(groups[0][0]):
            bad.append((anim, "transparent"))

    assert checked > 100, f"only {checked} sprites available to check"
    assert not bad, f"{len(bad)}/{checked} corpus sprites decoded wrong: {bad[:10]}"
    # Most of the map's sprites should be present; a few obscure DEFs may be absent.
    assert len(absent) <= 5, f"{len(absent)} sprites missing from LOD: {absent[:10]}"


def test_render_is_deterministic() -> None:
    """The same terrain + objects render to byte-identical pixels every time."""
    surf = [[f"gr{(x + y) % 4}_" for x in range(6)] for y in range(6)]
    objs = [
        PlacedObject(4, 4, 0, "", "", None, "AVLpntr7", ()),
        PlacedObject(2, 5, 0, "", "", None, "AVLman30", ()),
    ]
    a = RE.render_map(surf, RE.paint_sort(objs))
    b = RE.render_map(surf, RE.paint_sort(objs))
    assert a.size == b.size
    assert a.tobytes() == b.tobytes(), "renderer is not deterministic"

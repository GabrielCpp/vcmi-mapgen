"""Reliability tests for the H3-sprite rendering engine (renderers/sprites.py).

These guard terrain-tile decoding, decode coverage over every sprite the engine
actually composites, and renderer determinism. The DEF decoder's own tests sit in
vcmi/formats/defs_test.py.

They require the local H3 sprite LOD files; the whole module is skipped when those
are absent (e.g. CI without a VCMI install).

Run: `uv run pytest vcmi_mapgen/renderers/sprites_test.py -q`
"""

import struct

import pytest
from PIL import Image

import vcmi_mapgen.renderers.sprites as RE
from vcmi_mapgen.conftest import corpus_map, find_install
from vcmi_mapgen.core.model import Footprint, PlacedObject
from vcmi_mapgen.vcmi.formats.lod import LOD_FILES, LodIndex, lod

TEST_MAP = "All for One"


_INSTALL = find_install()
DATA_DIR = _INSTALL.data_dir if _INSTALL is not None else None
pytestmark = pytest.mark.skipif(
    DATA_DIR is None or not any((DATA_DIR / f).exists() for f in LOD_FILES),
    reason="H3 sprite LOD files not found (set VCMI_HOME)",
)


def _index() -> LodIndex:
    assert DATA_DIR is not None
    return lod(DATA_DIR)


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


def test_every_terrain_tile_decodes() -> None:
    """Every terrain .def decodes, and terr_tile_img yields a 32x32 non-empty tile."""
    for tc, defname in RE.TERR_DEF.items():
        groups = RE.get_def(_index(), defname)
        assert groups and groups[0], f"terrain {tc} ({defname}) failed to decode"
        tile = RE.terr_tile_img(_index(), f"{tc}0_")
        assert tile.size == (RE.TILE, RE.TILE), f"{tc}: tile size {tile.size}"
        assert _nonempty(tile), f"{tc} ({defname}): terrain tile is fully transparent"


def test_decode_coverage_over_corpus_sprites() -> None:
    """Reliability sweep: every distinct object sprite the engine would composite for
    the test map must, when present in the LOD, decode to a non-empty frame of the
    header-declared size. Sprites genuinely absent from the LOD are reported, not
    failed (that is a data-availability issue, not a decoder fault)."""
    fm = corpus_map(TEST_MAP)
    anims = sorted({o.kind for o in fm.objs if o.kind})
    assert anims, "no object animations found in the test map"

    absent: list[str] = []
    bad: list[tuple[str, str]] = []
    checked = 0
    for anim in anims:
        data = _index().read(anim)
        if not data or len(data) < 40:  # not in LOD (data availability, not decoder)
            absent.append(anim)
            continue
        checked += 1
        try:
            _comp, fullw, fullh = _first_frame_header(anim)
            groups = RE.get_def(_index(), anim)
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
        PlacedObject(4, 4, 0, "", "AVLpntr7", Footprint(0, 0, ())),
        PlacedObject(2, 5, 0, "", "AVLman30", Footprint(0, 0, ())),
    ]
    a = RE.render_map(_index(), surf, objs)
    b = RE.render_map(_index(), surf, objs)
    assert a.size == b.size
    assert a.tobytes() == b.tobytes(), "renderer is not deterministic"

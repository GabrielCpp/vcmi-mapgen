"""Reliability tests for the H3-sprite rendering engine (renderers/sprites.py).

These guard terrain-tile decoding, decode coverage over every sprite the engine
actually composites, and renderer determinism. The DEF decoder's own tests sit in
vcmi/formats/defs_test.py.

They require the local H3 sprite LOD files; the whole module is skipped when those
are absent (e.g. CI without a VCMI install).

Run: `uv run pytest vcmi_mapgen/renderers/sprites_test.py -q`
"""

import io
import json
import struct
from pathlib import Path

import pytest
from PIL import Image

import vcmi_mapgen.renderers.sprites as RE
from vcmi_mapgen.conftest import corpus_map, find_install
from vcmi_mapgen.core.model import Footprint, PlacedObject
from vcmi_mapgen.vcmi.content.archive import FolderArchive, open_archive
from vcmi_mapgen.vcmi.content.sprites import SpriteSource
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
        if not defname.endswith(RE.DEF_SUFFIX):
            continue
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


def _png(colour: tuple[int, int, int]) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (RE.TILE, RE.TILE), colour).save(buf, "PNG")
    return buf.getvalue()


def test_a_json_animation_loads_its_group_zero_frames(tmp_path: Path) -> None:
    doc = {"basepath": "hota/hl/", "sequences": [{"group": 0, "frames": ["b.png", "a.png"]}]}
    files = {"hota/hl.json": json.dumps(doc).encode(), "hota/hl/a.png": _png((1, 2, 3))}
    files["hota/hl/b.png"] = _png((4, 5, 6))
    for name, data in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_bytes(data)
    groups = RE.get_def(FolderArchive(tmp_path), "hota/hl")
    assert groups is not None
    assert [f.getpixel((0, 0)) for f in groups[0]] == [(4, 5, 6, 255), (1, 2, 3, 255)]


HOTA_TERRAIN_MODS = ("highlandsTerrain", "wastelandTerrain")


def _hota_sprites() -> SpriteSource | None:
    if _INSTALL is None:
        return None
    folders = [_INSTALL.mods_dir / "hota" / "mods" / m for m in HOTA_TERRAIN_MODS]
    if not all(f.is_dir() for f in folders):
        return None
    return SpriteSource(_index(), [open_archive(f) for f in folders])


@pytest.mark.skipif(_hota_sprites() is None, reason="needs the HotA terrain mods")
def test_hota_terrain_tiles_come_from_their_mods() -> None:
    source = _hota_sprites()
    assert source is not None
    for tc in ("hl", "ws"):
        tile = RE.terr_tile_img(source, f"{tc}0_")
        assert tile.size == (RE.TILE, RE.TILE)
        assert tile.getpixel((5, 5)) not in ((40, 40, 40, 255), (80, 40, 80, 255)), tc
        assert _nonempty(tile), tc

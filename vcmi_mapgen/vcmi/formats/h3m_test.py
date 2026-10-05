import gzip
import struct
import zipfile
from pathlib import Path

import pytest

from vcmi_mapgen.conftest import SETTINGS, find_install
from vcmi_mapgen.vcmi.formats.h3m import (
    HOTA,
    SOD,
    H3Map,
    H3MParser,
    Reader,
    features_for,
    hota_features,
    parse_file,
)
from vcmi_mapgen.vcmi.formats.h3m_scripts import HotaScripts, ScriptError

TAIL = 124
HIGHLANDS = 10
FILLER = b"\x7f"
HOTA_MAPS = ("hota", "mods", "maps", "Mods")
MAP_PACKS = ("officialMaps", "famousMaps")
CONTENT = "content.zip"


def _u32(v: int) -> bytes:
    return struct.pack("<I", v)


def _hota_header(version: int) -> bytes:
    out = _u32(HOTA) + _u32(version)
    if version >= 8:
        out += FILLER * 12
    if version >= 1:
        out += FILLER * 2
    if version >= 2:
        out += _u32(7)
    if version >= 5:
        out += _u32(7) + b"\x01"
    out += b"\x01" * ((version >= 7) + (version >= 8))
    if version >= 9:
        out += _u32(7)
    return out


def _map_options(version: int) -> bytes:
    out = bytes(31) + b"\x01" + bytes(3)
    if version >= 1:
        out += _u32(8) + b"\xff"
    if version >= 3:
        out += _u32(7)
    if version >= 5:
        out += FILLER * 8
    return out


def _hota_map(version: int, size: int = 2) -> bytes:
    """A whole HotA map at ``version``: no players, objects or events, highlands everywhere."""
    unplayable = bytes(2 + 6 + 6 + 1)
    out = _hota_header(version) + b"\x01" + _u32(size) + b"\x00" + _u32(0) + _u32(0) + b"\x01\x00"
    out += unplayable * 8 + b"\xff\xff" + b"\x00"
    out += _u32(0) + _u32(0) + b"\x00"
    out += _map_options(version)
    if version >= 9:
        out += b"\x00"
    out += _u32(0) + bytes(9 + 4) + _u32(0) + _u32(0)
    out += bytes([HIGHLANDS, 0, 0, 0, 0, 0, 0]) * size * size
    return out + _u32(0) + _u32(0) + _u32(0) + bytes(TAIL)


def _assert_whole(m: H3Map) -> None:
    assert m.bytes_remaining == TAIL
    assert m.remaining_all_zero


def test_hota_features_grow_by_sub_version() -> None:
    assert features_for(HOTA, 0).hota == 0
    assert features_for(HOTA, 0).terrains_count == 12
    assert features_for(HOTA, 2).artifacts_count == 163
    assert features_for(HOTA, 3).artifacts_count == 165
    assert features_for(HOTA, 5).factions_count == 11
    assert features_for(HOTA, 9).factions_count == 12
    assert features_for(HOTA, 9).hota_at(9)
    assert not features_for(SOD).hota_at(0)


def test_an_unknown_format_or_hota_version_is_refused() -> None:
    with pytest.raises(ValueError):
        _ = hota_features(10)
    with pytest.raises(ValueError):
        _ = features_for(0x33)


@pytest.mark.parametrize("version", range(10))
def test_a_synthetic_hota_map_parses_to_its_tail(version: int) -> None:
    m = H3MParser(_hota_map(version)).parse("synthetic")
    assert (m.fmt, m.hota_version, m.width) == (HOTA, version, 2)
    assert {t.terrain for row in m.terrain[0] for t in row} == {HIGHLANDS}
    _assert_whole(m)


def test_a_gzipped_hota_map_reads_from_disk(tmp_path: Path) -> None:
    path = tmp_path / "tiny.h3m"
    _ = path.write_bytes(gzip.compress(_hota_map(9)))
    m = parse_file(str(path))
    assert m.name == "tiny"
    _assert_whole(m)


def test_a_sized_bitmask_reads_its_own_bit_count() -> None:
    r = Reader(_u32(10) + b"\x05\x02", features_for(HOTA, 9))
    assert r.bitmask_sized() == [0, 2, 9]
    assert r.pos == 6


def _scripts(body: bytes) -> Reader:
    return Reader(body, features_for(HOTA, 9))


def test_an_inactive_script_section_is_one_byte() -> None:
    r = _scripts(b"\x00\x01")
    HotaScripts(r).skip_section()
    assert r.pos == 1


def _event(action_code: int) -> bytes:
    actions = _u32(0) + b"\x00" + _u32(1) + _u32(action_code)
    return _u32(1) + _u32(3) + actions + _u32(2) + b"hi"


def test_an_active_script_section_walks_its_events() -> None:
    body = b"\x01" + _event(5) + _u32(0) * 3 + _u32(0) * 5 + _u32(0) + _u32(0) * 5
    r = _scripts(body + b"\x01")
    HotaScripts(r).skip_section()
    assert r.pos == len(body)


def test_an_unknown_script_action_is_refused() -> None:
    with pytest.raises(ScriptError):
        HotaScripts(_scripts(b"\x01" + _event(99))).skip_section()


def _smallest_per_version(archives: list[Path]) -> list[tuple[str, bytes]]:
    found: dict[int, tuple[str, bytes]] = {}
    for path in archives:
        with zipfile.ZipFile(path) as z:
            for name in sorted(n for n in z.namelist() if n.lower().endswith(".h3m")):
                data = gzip.decompress(z.read(name))
                version = struct.unpack_from("<I", data, 4)[0]
                if version not in found or len(data) < len(found[version][1]):
                    found[version] = (name, data)
    return [found[v] for v in sorted(found)]


def _hota_archives() -> list[Path]:
    install = find_install()
    if install is None:
        return []
    root = install.mods_dir.joinpath(*HOTA_MAPS)
    return [p for p in (root / pack / CONTENT for pack in MAP_PACKS) if p.is_file()]


@pytest.mark.skipif(not _hota_archives(), reason="needs the HotA mod's map packs")
def test_real_hota_maps_of_every_sub_version_parse_to_their_tail() -> None:
    maps = _smallest_per_version(_hota_archives())
    assert len(maps) > 1
    for name, data in maps:
        m = H3MParser(data).parse(name)
        assert m.fmt == HOTA, name
        _assert_whole(m)


CORPUS_MAPS = ("A Warm and Familiar Place", "All for One", "Carpe Diem")


@pytest.mark.skipif(not SETTINGS.h3m_dir.is_dir(), reason="needs the .h3m corpus")
def test_base_format_corpus_maps_still_parse_to_their_tail() -> None:
    for name in CORPUS_MAPS:
        path = SETTINGS.h3m_dir / f"{name}.h3m"
        m = parse_file(str(path))
        assert m.fmt != HOTA and m.hota_version == -1, path.name
        _assert_whole(m)

"""Reliability tests for cli.generate overlay selection (parse_overlays)."""

from pathlib import Path

from vcmi_mapgen.cli.generate import (
    DEFAULT_OVERLAYS,
    INSTALL_FOLDER,
    file_stem,
    install_map,
    parse_overlays,
)
from vcmi_mapgen.renderers.overlays import ZoneOverlay
from vcmi_mapgen.vcmi.install import VcmiInstall


def test_zone_label_composites_last_regardless_of_requested_order() -> None:
    """PngRenderer.render composites overlays IN LIST ORDER (each later one painted
    over the earlier ones) -- so a zone-id label must be the LAST entry whenever
    "zone" is requested, or a later overlay (blocking/guard/pocket) buries it. This
    held even when "zone" was the first name in the spec, which is the reported bug:
    the default overlay order is "zone,blocking,guard,pocket"."""
    overlays = parse_overlays("zone,blocking,pocket", {}, {})
    assert isinstance(overlays[-1], ZoneOverlay)
    assert overlays[-1].labels is True
    assert overlays[-1].fill is False, "the trailing zone pass must be label-only"
    # the in-position "zone" entry must be fill-only, so the label isn't drawn twice
    zone_entries = [o for o in overlays if isinstance(o, ZoneOverlay)]
    assert len(zone_entries) == 2
    assert zone_entries[0].fill is True and zone_entries[0].labels is False


def test_zone_not_requested_no_trailing_label_pass() -> None:
    overlays = parse_overlays("blocking,pocket", {}, {})
    assert not any(isinstance(o, ZoneOverlay) for o in overlays)


def test_passage_overlay_not_in_default_selection() -> None:
    """The blue walkable-seam overlay must not render by default."""
    assert "passage" not in DEFAULT_OVERLAYS.split(",")


def test_file_stem_keeps_a_plain_title() -> None:
    assert file_stem("Twin Lakes") == "Twin Lakes"


def test_file_stem_replaces_the_characters_a_file_system_refuses() -> None:
    assert file_stem('a/b\\c:d*e?f"g<h>i|j') == "a_b_c_d_e_f_g_h_i_j"


def test_install_map_copies_into_the_pp_gen_folder(tmp_path: Path) -> None:
    vmap = tmp_path / "out" / "Twin Lakes.vmap"
    vmap.parent.mkdir()
    _ = vmap.write_bytes(b"map")
    install = VcmiInstall(tmp_path / "vcmi", tmp_path / "vcmi" / "Data", ())
    installed = install_map(str(vmap), install)
    assert installed == tmp_path / "vcmi" / "Maps" / INSTALL_FOLDER / "Twin Lakes.vmap"
    assert installed.read_bytes() == b"map"

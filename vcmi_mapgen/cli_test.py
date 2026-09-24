"""Reliability tests for cli.py's overlay selection (parse_overlays)."""

from vcmi_mapgen.cli import DEFAULT_OVERLAYS, parse_overlays
from vcmi_mapgen.renderers.overlays import ZoneOverlay


def test_zone_label_composites_last_regardless_of_requested_order() -> None:
    """PngRenderer.render composites overlays IN LIST ORDER (each later one painted
    over the earlier ones) -- so a zone-id label must be the LAST entry whenever
    "zone" is requested, or a later overlay (blocking/guard/pocket) buries it. This
    held even when "zone" was the first name in the spec, which is the reported bug:
    the default overlay order is "zone,blocking,guard,pocket"."""
    overlays = parse_overlays("zone,blocking,pocket", {})
    assert isinstance(overlays[-1], ZoneOverlay)
    assert overlays[-1].labels is True
    assert overlays[-1].fill is False, "the trailing zone pass must be label-only"
    # the in-position "zone" entry must be fill-only, so the label isn't drawn twice
    zone_entries = [o for o in overlays if isinstance(o, ZoneOverlay)]
    assert len(zone_entries) == 2
    assert zone_entries[0].fill is True and zone_entries[0].labels is False


def test_zone_not_requested_no_trailing_label_pass() -> None:
    overlays = parse_overlays("blocking,pocket", {})
    assert not any(isinstance(o, ZoneOverlay) for o in overlays)


def test_passage_overlay_not_in_default_selection() -> None:
    """The blue walkable-seam overlay must not render by default."""
    assert "passage" not in DEFAULT_OVERLAYS.split(",")

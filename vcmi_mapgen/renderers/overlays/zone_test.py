from vcmi_mapgen.models import MapState
from vcmi_mapgen.renderers.overlays.zone import ZoneOverlay

TILE = 32


def _cell(t=2):
    return {"t": t, "view": 0, "rt": 0, "rd": 0, "ot": 0, "od": 0, "m": 0}


def _state():
    grid = [[_cell() for _ in range(4)] for _ in range(4)]
    ts = {(x, y) for y in range(4) for x in range(4)}
    zones = {0: {"tiles_set": ts, "terrain_type": 2, "area": len(ts), "centroid": (2, 2)}}
    return MapState(cells={0: grid}, surfs={0: grid}, objs=[], zones={0: zones})


def _centroid_px(img):
    return img.load()[2 * TILE + TILE // 2, 2 * TILE + TILE // 2]


def _any_opaque_near_centroid(img):
    """The label glyph doesn't necessarily cover the exact center pixel (e.g. '0'
    is hollow there), so scan the small box around the centroid instead."""
    px = img.load()
    cx, cy = 2 * TILE + TILE // 2, 2 * TILE + TILE // 2
    return any(px[cx + dx, cy + dy][3] == 255
               for dx in range(-10, 11) for dy in range(-10, 11))


def test_fill_false_draws_no_fill_pixels():
    """A label-only pass must not paint the zone tint -- every tile away from
    the centroid label stays fully transparent."""
    img = ZoneOverlay(fill=False).apply(_state(), 0)
    corner = img.load()[0, 0]
    assert corner[3] == 0, f"fill=False still painted a fill pixel: {corner}"


def test_fill_false_still_draws_the_label():
    """The label-only pass is the one PngRenderer composites last (see
    cli._parse_overlays) -- it must still carry the zone-id text."""
    img = ZoneOverlay(fill=False).apply(_state(), 0)
    assert _any_opaque_near_centroid(img), "no opaque label pixel found near the centroid"


def test_labels_false_draws_fill_but_no_label():
    """The default in-stack pass (fill only) must not also draw a label --
    the centroid pixel's alpha must be exactly the fill alpha, not the
    label's opaque 255."""
    img = ZoneOverlay(labels=False, fill_alpha=55).apply(_state(), 0)
    px = _centroid_px(img)
    assert px[3] == 55, f"expected plain fill alpha 55 at centroid, got {px[3]}"

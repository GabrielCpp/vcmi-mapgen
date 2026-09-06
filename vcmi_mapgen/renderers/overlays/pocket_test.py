from vcmi_mapgen.models import MapState
from vcmi_mapgen.renderers.overlays.pocket import PocketOverlay, _magenta_color

TILE = 32


def _tinted_tiles(img):
    px = img.load()
    return {(x // TILE, y // TILE)
            for y in range(0, img.height, TILE) for x in range(0, img.width, TILE)
            if px[x, y][3] > 0}


def test_overlay_renders_exactly_the_tiles_it_was_given():
    """PocketOverlay performs no detection of its own -- it paints exactly the tiles
    in the `pockets` dict it was constructed with (RepairStep's ctx["pockets"]),
    nothing more, nothing less."""
    state = MapState(size=6)
    pockets = {0: {(2, 3): 0.0, (2, 4): 1.0}}
    tinted = _tinted_tiles(PocketOverlay(pockets).apply(state, 0))
    assert tinted == {(2, 3), (2, 4)}


def test_overlay_colors_by_the_stored_depth_not_recomputed_geometry():
    state = MapState(size=6)
    pockets = {0: {(1, 1): 0.0, (1, 2): 1.0}}
    img = PocketOverlay(pockets).apply(state, 0)
    px = img.load()
    assert px[1 * TILE, 1 * TILE] == _magenta_color(0.0)
    assert px[1 * TILE, 2 * TILE] == _magenta_color(1.0)
    assert px[1 * TILE, 1 * TILE] != px[1 * TILE, 2 * TILE]


def test_a_different_level_or_no_pockets_at_all_renders_nothing():
    state = MapState(size=6)
    assert _tinted_tiles(PocketOverlay({0: {(1, 1): 0.5}}).apply(state, 1)) == set()
    assert _tinted_tiles(PocketOverlay().apply(state, 0)) == set()

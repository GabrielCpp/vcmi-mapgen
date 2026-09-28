from PIL import Image

from vcmi_mapgen.core.model import MapState, Tile
from vcmi_mapgen.renderers.overlays.pocket import PocketOverlay, magenta_color

TILE = 32


def _rgba_at(img: Image.Image, x: int, y: int) -> tuple[int, int, int, int]:
    offset = (y * img.width + x) * 4
    r, g, b, a = img.tobytes()[offset : offset + 4]
    return r, g, b, a


def _tinted_tiles(img: Image.Image) -> set[Tile]:
    alpha = img.getchannel("A").tobytes()
    return {
        (x // TILE, y // TILE)
        for y in range(0, img.height, TILE)
        for x in range(0, img.width, TILE)
        if alpha[y * img.width + x] > 0
    }


def test_overlay_renders_exactly_the_tiles_it_was_given() -> None:
    """PocketOverlay performs no detection of its own -- it paints exactly the tiles
    in the `pockets` dict it was constructed with (LootStep's LootResult.pockets),
    nothing more, nothing less."""
    state = MapState(size=6)
    pockets: dict[int, dict[Tile, float]] = {0: {(2, 3): 0.0, (2, 4): 1.0}}
    tinted = _tinted_tiles(PocketOverlay(pockets).apply(state, 0))
    assert tinted == {(2, 3), (2, 4)}


def test_overlay_colors_by_the_stored_depth_not_recomputed_geometry() -> None:
    state = MapState(size=6)
    pockets: dict[int, dict[Tile, float]] = {0: {(1, 1): 0.0, (1, 2): 1.0}}
    img = PocketOverlay(pockets).apply(state, 0)
    shallow = _rgba_at(img, 1 * TILE, 1 * TILE)
    deep = _rgba_at(img, 1 * TILE, 2 * TILE)
    assert shallow == magenta_color(0.0)
    assert deep == magenta_color(1.0)
    assert shallow != deep


def test_a_different_level_or_no_pockets_at_all_renders_nothing() -> None:
    state = MapState(size=6)
    assert _tinted_tiles(PocketOverlay({0: {(1, 1): 0.5}}).apply(state, 1)) == set()
    assert _tinted_tiles(PocketOverlay().apply(state, 0)) == set()

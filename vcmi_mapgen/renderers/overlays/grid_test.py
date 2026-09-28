from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.renderers.overlays.grid import GridOverlay

TILE = 32


def _state(w: int, h: int) -> MapState:
    grid = [[Terrain.GRASS for _ in range(w)] for _ in range(h)]
    return MapState(size=max(w, h), terrain={0: grid}, objs=[])


def test_grid_matches_map_size_and_draws_every_tile_edge() -> None:
    img = GridOverlay().apply(_state(12, 8), 0)
    assert img.size == (12 * TILE, 8 * TILE)
    alpha = img.getchannel("A")
    assert alpha.getpixel((7 * TILE, 4 * TILE + 16)) != 0
    assert alpha.getpixel((5 * TILE + 16, 7 * TILE)) != 0


def test_grid_leaves_tile_interiors_clear() -> None:
    img = GridOverlay().apply(_state(12, 8), 0)
    assert img.getchannel("A").getpixel((3 * TILE + 16, 3 * TILE + 24)) == 0

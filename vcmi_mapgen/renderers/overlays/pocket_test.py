from vcmi_mapgen.pipeline import MapState
from vcmi_mapgen.renderers.overlays.pocket import PocketOverlay, _sealed_regions

TILE = 32
_ROCK = 9


def _cell(t=2):
    return {"t": t, "view": 0, "rt": 0, "rd": 0, "ot": 0, "od": 0, "m": 0}


def _grid(w, h, rocks=()):
    g = [[_cell() for _ in range(w)] for _ in range(h)]
    for (x, y) in rocks:
        g[y][x] = _cell(_ROCK)
    return g


def _tinted_tiles(img):
    px = img.load()
    return {(x // TILE, y // TILE)
            for y in range(0, img.height, TILE) for x in range(0, img.width, TILE)
            if px[x, y][3] > 0}


def _one_tile_alcove_scenario():
    """A guard at (7,2) whose 3x3 ZoC (x 6-8) is the only way to reach the
    single-tile alcove (9,2) -- rock above/below it, the map's right edge to its
    east. Everywhere else is wide open (way over the 14-tile sealed-region cap),
    so only the alcove counts as sealed."""
    W, H = 10, 5
    grid = _grid(W, H, rocks=[(9, 1), (9, 3)])
    guard = {"x": 7, "y": 2, "l": 0, "purpose": "GUARD", "mask": ["A"]}
    return grid, [guard], W, H


def test_guard_seals_a_one_tile_alcove():
    grid, objs, W, H = _one_tile_alcove_scenario()
    passable = {(x, y) for y in range(H) for x in range(W)} - {(9, 1), (9, 3)}
    regions = _sealed_regions(objs, 0, passable, W, H)
    assert len(regions) == 1
    zoc, sealed = regions[0]
    assert sealed == {(9, 2)}
    assert zoc == {(gx, gy) for gx in (6, 7, 8) for gy in (1, 2, 3)}


def test_overlay_tints_only_the_sealed_alcove_not_the_open_field():
    grid, objs, W, H = _one_tile_alcove_scenario()
    state = MapState(cells={0: grid}, surfs={0: grid}, objs=objs)
    tinted = _tinted_tiles(PocketOverlay().apply(state, 0))
    assert tinted == {(9, 2)}


def test_no_guard_means_no_sealed_regions():
    grid = _grid(6, 6)
    state = MapState(cells={0: grid}, surfs={0: grid}, objs=[])
    assert _tinted_tiles(PocketOverlay().apply(state, 0)) == set()

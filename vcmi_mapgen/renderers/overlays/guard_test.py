from vcmi_mapgen.models import MapState
from vcmi_mapgen.renderers.overlays.guard import GuardOverlay

TILE = 32


def _cell(t=2):
    return {"t": t, "view": 0, "rt": 0, "rd": 0, "ot": 0, "od": 0, "m": 0}


def _tinted_tiles(img):
    px = img.load()
    return {(x // TILE, y // TILE)
            for y in range(0, img.height, TILE) for x in range(0, img.width, TILE)
            if px[x, y][3] > 0}


def test_guard_zoc_covers_the_3x3_around_the_interactive_cell():
    grid = [[_cell() for _ in range(10)] for _ in range(10)]
    guard = {"x": 5, "y": 5, "l": 0, "purpose": "GUARD", "mask": ["A"]}
    state = MapState(cells={0: grid}, surfs={0: grid}, objs=[guard])

    img = GuardOverlay().apply(state, 0)
    tinted = _tinted_tiles(img)
    expected = {(5 + dx, 5 + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
    assert tinted == expected


def test_guard_zoc_clips_to_the_map_edge():
    grid = [[_cell() for _ in range(10)] for _ in range(10)]
    guard = {"x": 0, "y": 0, "l": 0, "purpose": "GUARD", "mask": ["A"]}
    state = MapState(cells={0: grid}, surfs={0: grid}, objs=[guard])

    tinted = _tinted_tiles(GuardOverlay().apply(state, 0))
    assert tinted == {(0, 0), (1, 0), (0, 1), (1, 1)}


def test_non_guard_and_other_level_objects_are_ignored():
    grid = [[_cell() for _ in range(6)] for _ in range(6)]
    objs = [
        {"x": 3, "y": 3, "l": 0, "purpose": "DECORATION", "mask": ["B"]},
        {"x": 3, "y": 3, "l": 1, "purpose": "GUARD", "mask": ["A"]},
    ]
    state = MapState(cells={0: grid}, surfs={0: grid}, objs=objs)
    assert _tinted_tiles(GuardOverlay().apply(state, 0)) == set()

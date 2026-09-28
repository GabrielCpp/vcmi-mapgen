from PIL import Image

from vcmi_mapgen.core.model import MapState, PlacedObject, Tile
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.renderers.overlays.guard import GuardOverlay
from vcmi_mapgen.vcmi.footprint import Mask, footprint_of

TILE = 32


def _cell(t: int = 2) -> Terrain:
    return Terrain(t)


def _obj(x: int, y: int, purpose: str, mask: Mask, level: int = 0) -> PlacedObject:
    return PlacedObject(
        x=x,
        y=y,
        level=level,
        purpose=purpose,
        kind="",
        footprint=footprint_of(mask),
    )


def _tinted_tiles(img: Image.Image) -> set[Tile]:
    alpha = img.getchannel("A").tobytes()
    return {
        (x // TILE, y // TILE)
        for y in range(0, img.height, TILE)
        for x in range(0, img.width, TILE)
        if alpha[y * img.width + x] > 0
    }


def test_guard_zoc_covers_the_3x3_around_the_interactive_cell() -> None:
    grid = [[_cell() for _ in range(10)] for _ in range(10)]
    guard = _obj(5, 5, "GUARD", ("A",))
    state = MapState(size=max(len(grid), len(grid[0])), terrain={0: grid}, objs=[guard])

    img = GuardOverlay().apply(state, 0)
    tinted = _tinted_tiles(img)
    expected = {(5 + dx, 5 + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
    assert tinted == expected


def test_guard_zoc_clips_to_the_map_edge() -> None:
    grid = [[_cell() for _ in range(10)] for _ in range(10)]
    guard = _obj(0, 0, "GUARD", ("A",))
    state = MapState(size=max(len(grid), len(grid[0])), terrain={0: grid}, objs=[guard])

    tinted = _tinted_tiles(GuardOverlay().apply(state, 0))
    assert tinted == {(0, 0), (1, 0), (0, 1), (1, 1)}


def test_non_guard_and_other_level_objects_are_ignored() -> None:
    grid = [[_cell() for _ in range(6)] for _ in range(6)]
    objs = [
        _obj(3, 3, "DECORATION", ("B",)),
        _obj(3, 3, "GUARD", ("A",), level=1),
    ]
    state = MapState(size=max(len(grid), len(grid[0])), terrain={0: grid}, objs=objs)
    assert _tinted_tiles(GuardOverlay().apply(state, 0)) == set()

from PIL import Image

from vcmi_mapgen.models import Cell, MapState, Tile, Zone
from vcmi_mapgen.renderers.overlays.passage import PassageOverlay

TILE = 32


def _cell(t: int = 2) -> Cell:
    return Cell(t=t)


def _zone(tiles: set[Tile], centroid: tuple[float, float]) -> Zone:
    return Zone(
        terrain_type=2,
        area=len(tiles),
        centroid=centroid,
        tiles=sorted(tiles),
        tiles_set=frozenset(tiles),
    )


def _tinted_tiles(img: Image.Image) -> set[Tile]:
    alpha = img.getchannel("A").tobytes()
    return {
        (x // TILE, y // TILE)
        for y in range(0, img.height, TILE)
        for x in range(0, img.width, TILE)
        if alpha[y * img.width + x] > 0
    }


def test_passage_tiles_sit_exactly_on_the_zone_seam() -> None:
    """A 6x4 field split into a left zone (x<3) and a right zone (x>=3): the
    passage overlay must mark only the two columns bordering the seam."""
    grid = [[_cell() for _ in range(6)] for _ in range(4)]
    left = {(x, y) for y in range(4) for x in range(3)}
    right = {(x, y) for y in range(4) for x in range(3, 6)}
    zones = {
        0: _zone(left, (1, 1.5)),
        1: _zone(right, (4, 1.5)),
    }
    state = MapState(cells={0: grid}, objs=[], zones={0: zones})

    tinted = _tinted_tiles(PassageOverlay().apply(state, 0))
    expected = {(x, y) for y in range(4) for x in (2, 3)}
    assert tinted == expected


def test_no_op_without_zones() -> None:
    grid = [[_cell() for _ in range(4)] for _ in range(4)]
    state = MapState(cells={0: grid}, objs=[])
    img = PassageOverlay().apply(state, 0)
    assert _tinted_tiles(img) == set()

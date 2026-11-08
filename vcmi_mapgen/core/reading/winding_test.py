"""The route winding on literal walkable sets: an open field walks straight, and walls
whose gaps alternate ends make the walk snake far past the line."""

from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.reading.winding import route_winding

SIDE = 28


def _field() -> set[Tile]:
    return {(x, y) for x in range(SIDE) for y in range(SIDE)}


def test_an_open_field_walks_the_straight_line() -> None:
    assert route_winding(_field(), SIDE) == 1.0


def test_walls_with_alternating_gaps_wind_the_walk() -> None:
    walls: set[Tile] = set()
    for i, x in enumerate(range(3, SIDE, 4)):
        gap = SIDE - 1 if i % 2 == 0 else 0
        walls |= {(x, y) for y in range(SIDE) if y != gap}
    winding = route_winding(_field() - walls, SIDE)
    assert winding is not None
    assert winding > 3


def test_no_pair_in_the_band_reads_none() -> None:
    assert route_winding({(0, 0), (1, 0)}, SIDE) is None

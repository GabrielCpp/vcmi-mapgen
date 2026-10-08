from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.steps.gameplay.shipyards import boardings

SHORE = ["..~", "#S~", "..~"]


def _cells(mark: str) -> set[Tile]:
    return {(x, y) for y, row in enumerate(SHORE) for x, c in enumerate(row) if c in mark}


def test_a_hero_boards_from_each_land_tile_beside_a_dock() -> None:
    water, land = _cells("~"), _cells(".")
    found = boardings(_cells("S"), water.__contains__, land.__contains__)
    assert found == [((2, 0), (1, 0)), ((2, 1), (1, 0)), ((2, 1), (1, 2)), ((2, 2), (1, 2))]


def test_a_shipyard_on_closed_land_offers_no_boarding() -> None:
    water = _cells("~")
    assert boardings(_cells("S"), water.__contains__, lambda _t: False) == []

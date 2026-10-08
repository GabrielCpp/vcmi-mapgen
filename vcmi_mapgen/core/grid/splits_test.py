from vcmi_mapgen.core.grid.splits import splits
from vcmi_mapgen.core.model import Tile


def _land(rows: list[str]) -> set[Tile]:
    return {(x, y) for y, row in enumerate(rows) for x, c in enumerate(row) if c == "."}


def _ring(x: int, y: int) -> set[Tile]:
    return {(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)}


CORRIDOR = [
    "......#......",
    "......#......",
    ".............",
    ".............",
    ".............",
    "......#......",
    "......#......",
]


def test_ring_across_a_corridor_splits_two_large_rooms() -> None:
    land = _land(CORRIDOR)
    assert splits(_ring(6, 3), land.__contains__, 15)


def test_ring_in_the_open_splits_nothing() -> None:
    land = _land(["." * 13] * 7)
    assert not splits(_ring(6, 3), land.__contains__, 15)


def test_small_piece_cut_off_is_no_split() -> None:
    land = _land(CORRIDOR)
    assert not splits(_ring(6, 3), land.__contains__, 40)


def test_two_sides_joined_far_away_are_one_piece() -> None:
    rows = [
        ".............",
        "......#......",
        ".............",
        ".............",
        ".............",
        "#####.#.#####",
        ".............",
    ]
    land = _land(rows)
    assert not splits(_ring(6, 3), land.__contains__, 15, margin=1)

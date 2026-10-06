"""Detours on drawn grids: ``#`` is closed, ``.`` is open and ``x`` is an open tile the
cut closes."""

from vcmi_mapgen.core.grid.detour import detours
from vcmi_mapgen.core.model import Tile


def _grid(drawn: str) -> tuple[set[Tile], set[Tile]]:
    rows = drawn.strip().splitlines()
    tiles = {(x, y): c for y, row in enumerate(rows) for x, c in enumerate(row)}
    return {t for t, c in tiles.items() if c != "#"}, {t for t, c in tiles.items() if c == "x"}


def _detours(drawn: str) -> bool:
    open_tiles, cut = _grid(drawn)
    return detours(cut, lambda t: t in open_tiles)


def test_closing_a_corridor_sends_the_hero_round_the_loop() -> None:
    assert _detours("""
.........
.#######.
.#######.
....x....
""")


def test_an_object_in_open_ground_leaves_a_way_round_it() -> None:
    assert not _detours("""
.......
..xx...
..xx...
.......
""")


def test_an_object_against_a_wall_leaves_its_front_joined() -> None:
    assert not _detours("""
#######
#.xxx.#
#.....#
#.....#
""")


def test_a_two_wide_corridor_keeps_a_diagonal_way_past_one_tile() -> None:
    assert not _detours("""
#######
...x...
.......
#######
""")


def test_closing_both_lanes_of_a_two_wide_corridor_detours() -> None:
    assert _detours("""
#######
...x...
...x...
#######
""")


def test_a_cut_on_closed_ground_parts_nothing() -> None:
    open_tiles, _cut = _grid("""
#######
...#...
...#...
#######
""")
    assert not detours({(3, 1), (3, 2)}, lambda t: t in open_tiles)

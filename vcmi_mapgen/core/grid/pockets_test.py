"""Reliability tests for core.grid.pockets (pocket detection and depth)."""

from vcmi_mapgen.core.grid import pockets as PK
from vcmi_mapgen.core.grid.pocket_masks import parse_masks
from vcmi_mapgen.core.model import Tile


def test_pocket_depths_increase_from_mouth_to_deepest_tile() -> None:
    """A straight 4-tile corridor pocket: depth must increase monotonically away from
    the mouth, and every pocket tile must get a depth (none left unreached)."""
    pocket = frozenset({(1, 0), (2, 0), (3, 0), (4, 0)})
    mouth = frozenset({(0, 0)})  # just outside the pocket, 8-adjacent to (1, 0)
    depths = PK.pocket_depths(pocket, mouth)
    assert set(depths) == pocket
    assert depths[(1, 0)] == 0
    assert depths[(2, 0)] == 1
    assert depths[(3, 0)] == 2
    assert depths[(4, 0)] == 3


def test_pocket_depths_takes_the_shortest_path_when_the_pocket_branches() -> None:
    """(2, 0) is reachable from the mouth via BOTH (1, 0) and (1, 1) at the same
    distance, and (3, 0) is one step deeper than either -- every tile gets its
    shortest 8-connected distance from the mouth, regardless of how many
    predecessors it has."""
    pocket = frozenset({(1, 0), (1, 1), (2, 0), (3, 0)})
    mouth = frozenset({(0, 0)})
    depths = PK.pocket_depths(pocket, mouth)
    assert depths[(1, 0)] == 0  # 8-adjacent to mouth
    assert depths[(1, 1)] == 0  # also 8-adjacent to mouth
    assert depths[(2, 0)] == 1  # one step from either (1,0) or (1,1)
    assert depths[(3, 0)] == 2  # one step deeper still


NO_ACCESS: frozenset[Tile] = frozenset()


MASKS = parse_masks(
    """
nook 1
XXX
X X
XGX

corridor 2
XXX
X X
X X
XGX
"""
)


def _reach(rows: list[str]) -> set[Tile]:
    return {(x, y) for y, r in enumerate(rows) for x, c in enumerate(r) if c == "."}


CORRIDOR = [
    ".......",
    "..#.#..",
    "..#.#..",
    "..#.#..",
    "..###..",
]


def test_find_pockets_keeps_the_largest_mask_behind_one_guard() -> None:
    reach = _reach(CORRIDOR)
    raw = PK.find_pockets(reach, MASKS, NO_ACCESS, NO_ACCESS)
    assert raw == {
        (3, 1): (frozenset({(3, 2), (3, 3)}), frozenset({(3, 1)})),
        (3, 2): (frozenset({(3, 3)}), frozenset({(3, 2)})),
    }
    (blob,) = PK.dedupe_pockets(raw, frozenset(reach))
    assert blob[0] == ((3, 1), frozenset({(3, 2), (3, 3)}), frozenset({(3, 1)}))


def test_find_pockets_rejects_a_pocket_holding_an_access_tile() -> None:
    assert PK.find_pockets(_reach(CORRIDOR), MASKS, frozenset({(3, 3)}), NO_ACCESS) == {}


def test_find_pockets_keeps_the_guard_off_an_occupied_tile() -> None:
    assert PK.find_pockets(_reach(CORRIDOR), MASKS, NO_ACCESS, frozenset({(3, 1)})) == {
        (3, 2): (frozenset({(3, 3)}), frozenset({(3, 2)}))
    }


def test_find_pockets_reads_the_map_edge_as_wall() -> None:
    reach = _reach(["#.#", "#.#", "..."])
    assert PK.find_pockets(reach, MASKS, NO_ACCESS, NO_ACCESS) == {
        (1, 1): (frozenset({(1, 0)}), frozenset({(1, 1)}))
    }


def test_find_pockets_finds_nothing_along_a_straight_wall() -> None:
    reach = _reach([".......", ".......", "#######", ".......", "......."])
    assert PK.find_pockets(reach, MASKS, NO_ACCESS, NO_ACCESS) == {}

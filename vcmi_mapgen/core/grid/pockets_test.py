"""Reliability tests for core.grid.pockets (pocket detection and depth)."""

from vcmi_mapgen.core.grid import pockets as PK
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.steps.loot.pockets import dedupe_pockets


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


def _open_field_with_room(
    room_tiles: set[Tile],
    mouth: tuple[Tile, Tile] = ((5, 4), (6, 4)),
    field_w: int = 15,
    field_h: int = 4,
) -> set[Tile]:
    """A big open field (rows 0..field_h-1) connected to `room_tiles` ONLY through the
    two 4-connected `mouth` tiles -- everything else around the room is a wall (simply
    absent from `reach`)."""
    field = {(x, y) for x in range(field_w) for y in range(field_h)}
    reach = field | set(mouth) | set(room_tiles)
    return reach


def _top_pocket(reach: set[Tile]) -> tuple[Tile, frozenset[Tile], frozenset[Tile]]:
    """find_pockets alone can return several overlapping raw candidates for the SAME
    physical nook (e.g. the true outer doorway, and an inner partition of the room that
    is technically also a valid-but-smaller 2-tile doorway) -- `core.steps.loot.pockets.
    dedupe_pockets` blob-merges those and keeps the best one, exactly as the real
    pipeline always calls it. Asserts exactly one physical nook was found and returns
    its (guard_tile, pocket, mouth_fs)."""
    raw = PK.find_pockets(reach)
    blobs = dedupe_pockets(raw, frozenset(reach))
    assert len(blobs) == 1, f"expected exactly one physical nook, got {len(blobs)}"
    return blobs[0][0]  # best candidate in the blob


def test_find_pockets_detects_the_two_tile_doorway_cavity() -> None:
    """A 4-tile room behind an EXACT 2-tile, 4-connected doorway is found, with the
    mouth being exactly those two doorway tiles."""
    room = {(5, 5), (6, 5), (5, 6), (6, 6)}
    reach = _open_field_with_room(room)
    _guard_tile, pocket, mouth_fs = _top_pocket(reach)
    assert pocket == frozenset(room)
    assert mouth_fs == frozenset({(5, 4), (6, 4)})


def test_find_pockets_mouth_is_always_exactly_two_tiles() -> None:
    room = {(5, 5), (6, 5)}
    reach = _open_field_with_room(room)
    _guard_tile, _pocket, mouth_fs = _top_pocket(reach)
    assert len(mouth_fs) == 2
    m1, m2 = sorted(mouth_fs)
    assert max(abs(m1[0] - m2[0]), abs(m1[1] - m2[1])) == 1
    assert m1[0] == m2[0] or m1[1] == m2[1]  # 4-connected, not diagonal


def test_find_pockets_rejects_a_cavity_over_ten_tiles() -> None:
    """A room of 11 tiles behind a 2-tile doorway must NOT be reported -- the cavity
    exceeds the user-mandated 1..10 tile window. (Small inner-partition candidates may
    still be found -- see _top_pocket -- but none may reach the full 11-tile room.)"""
    room = {(x, y) for x in range(5, 9) for y in range(5, 8)}  # 4x3 = 12 tiles
    room = set(list(room)[:11])  # trim to exactly 11 for an unambiguous over-the-line case
    reach = _open_field_with_room(room)
    pockets = PK.find_pockets(reach)
    assert all(len(pocket) < 11 for pocket, _mouth in pockets.values())


def test_find_pockets_accepts_exactly_ten_tiles() -> None:
    room = {(x, y) for x in range(5, 7) for y in range(5, 10)}  # 2x5 = 10 tiles
    reach = _open_field_with_room(room, mouth=((5, 4), (6, 4)))
    _guard_tile, pocket, _mouth = _top_pocket(reach)
    assert len(pocket) == 10


def test_find_pockets_guard_tile_is_one_of_the_mouth_tiles() -> None:
    """Both mouth tiles sit within Chebyshev 1 of the reported guard_tile -- a single
    guard standing there has both inside its 3x3 zone of control (the "same monster
    zoc" requirement is automatic for any 4-connected pair, since they're always
    Chebyshev-1 apart)."""
    room = {(5, 5), (6, 5), (5, 6), (6, 6)}
    reach = _open_field_with_room(room)
    guard_tile, _pocket, mouth_fs = _top_pocket(reach)
    assert guard_tile in mouth_fs
    for m in mouth_fs:
        assert max(abs(guard_tile[0] - m[0]), abs(guard_tile[1] - m[1])) <= 1

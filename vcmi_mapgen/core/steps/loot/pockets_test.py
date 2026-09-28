"""Tests for the pocket geometry the guarded caches build on."""

from vcmi_mapgen.core.grid.pockets import dedupe_pockets, find_pockets
from vcmi_mapgen.core.model import Tile


def _field(w: int, h: int, walls: set[Tile]) -> set[Tile]:
    return {(x, y) for x in range(w) for y in range(h)} - walls


def test_find_pockets_drawn_shapes() -> None:
    """Regression fixture from the user's own drawings, updated 2026-09 for the 2-tile
    doorway model (a pocket's mouth is exactly two 4-connected tiles, replacing the
    single-guard-3x3-zone-of-control model this superseded). A flat 1-2 tile nook whose
    flanking walls do NOT protrude past its front (open diagonals on both sides) is no
    longer detectable: H3 diagonal movement gives it THREE independent entrances (front
    + both diagonals), and only 2 tiles can never block all three at once -- this is a
    real, accepted narrowing from the previous model, not a bug (see core.grid.pockets.
    find_pockets' docstring). A nook whose flanking walls DO protrude (blocking the
    diagonals) still has only one real approach and remains detectable as a 2-tile
    doorway (entrance tile + the tile behind it, in the approach direction)."""

    def best_mouths(reach: set[Tile], pocket_tiles: set[Tile]) -> list[frozenset[Tile]]:
        """canonical (deduped, ranked) mouth candidates whose pocket covers the nook"""
        raw = {g: c for g, c in find_pockets(reach).items() if set(pocket_tiles) <= c[0]}
        return [cands[0][2] for cands in dedupe_pockets(raw, reach)]

    # Flat 1-tile nook, open diagonals on both sides -- no longer sealable by 2 tiles.
    #     . . .
    #     X o X
    #     X X X
    reach = _field(12, 12, {(4, 5), (6, 5), (4, 6), (5, 6), (6, 6)})
    assert best_mouths(reach, {(5, 5)}) == []

    # Flat 2-tile nook, open diagonals -- same reason, no longer sealable.
    reach = _field(12, 12, {(3, 5), (6, 5), (3, 6), (4, 6), (5, 6), (6, 6)})
    assert best_mouths(reach, {(4, 5), (5, 5)}) == []

    # Protruding-corner nook: flanking walls block both diagonals, leaving exactly one
    # approach -- still detectable, mouth = the entrance tile + the tile behind it.
    reach = _field(12, 12, {(4, 4), (6, 4), (4, 5), (6, 5), (4, 6), (5, 6), (6, 6)})
    (mouth_fs,) = best_mouths(reach, {(5, 5)})
    assert mouth_fs == frozenset({(5, 3), (5, 4)})

    # Dead-end corridor -- 2-tile doorway at the corridor entrance, treasures behind.
    #     X X X X X X
    #     X . . . . .
    #     X X X X X X
    walls = {(x, 5) for x in range(2, 8)} | {(2, 6)} | {(x, 7) for x in range(2, 8)}
    (mouth_fs,) = best_mouths(_field(14, 14, walls), {(3, 6), (4, 6), (5, 6), (6, 6)})
    assert mouth_fs == frozenset({(7, 6), (8, 6)})

    # Bent corridor, user's `O` = guard opening, `P` = treasure tiles
    #       X X X X X X
    #     X X X P P P P O
    #     X P P P X X X X
    #     X X X X X
    walls = (
        {(x, 5) for x in range(5, 11)}
        | {(x, 6) for x in range(3, 6)}
        | {(3, 7)}
        | {(x, 7) for x in range(7, 11)}
        | {(x, 8) for x in range(3, 8)}
    )
    P = {(6, 6), (7, 6), (8, 6), (9, 6), (4, 7), (5, 7), (6, 7)}
    (mouth_fs,) = best_mouths(_field(20, 20, walls), P)
    assert mouth_fs == frozenset({(10, 6), (11, 6)})

    # control: a lone straight wall through an open field must yield no pocket anywhere,
    # including its two ends against the map edge (no 2-tile doorway sealing them either).
    reach = _field(12, 12, {(x, 6) for x in range(12)})
    assert find_pockets(reach) == {}

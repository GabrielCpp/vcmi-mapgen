"""Tests for the pocket geometry the guarded caches build on."""

from vcmi_mapgen.core.grid.pockets import dedupe_pockets, find_pockets
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.priors.bundle import Priors

NO_ACCESS: frozenset[Tile] = frozenset()


def _field(w: int, h: int, walls: set[Tile]) -> set[Tile]:
    return {(x, y) for x in range(w) for y in range(h)} - walls


def test_find_pockets_drawn_shapes(priors: Priors) -> None:
    def best_mouths(reach: set[Tile], pocket_tiles: set[Tile]) -> list[frozenset[Tile]]:
        found = find_pockets(reach, priors.pocket_masks, NO_ACCESS, NO_ACCESS)
        raw = {g: c for g, c in found.items() if set(pocket_tiles) <= c[0]}
        return [cands[0][2] for cands in dedupe_pockets(raw, frozenset(reach))]

    reach = _field(12, 12, {(4, 5), (6, 5), (4, 6), (5, 6), (6, 6)})
    assert best_mouths(reach, {(5, 5)}) == []

    reach = _field(12, 12, {(3, 5), (6, 5), (3, 6), (4, 6), (5, 6), (6, 6)})
    assert best_mouths(reach, {(4, 5), (5, 5)}) == []

    reach = _field(12, 12, {(4, 4), (6, 4), (4, 5), (6, 5), (4, 6), (5, 6), (6, 6)})
    (mouth_fs,) = best_mouths(reach, {(5, 5)})
    assert mouth_fs == frozenset({(5, 4)})

    walls = {(x, 5) for x in range(2, 8)} | {(2, 6)} | {(x, 7) for x in range(2, 8)}
    reach = _field(14, 14, walls)
    (mouth_fs,) = best_mouths(reach, {(3, 6), (4, 6), (5, 6), (6, 6)})
    assert mouth_fs == frozenset({(7, 6)})

    reach = _field(12, 12, {(x, 6) for x in range(12)})
    assert find_pockets(reach, priors.pocket_masks, NO_ACCESS, NO_ACCESS) == {}

import random

from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.planning.loot_zones import choose_loot_zones, draw_loot_zones, passage


def _box(x0: int, y0: int, x1: int, y1: int) -> frozenset[Tile]:
    return frozenset((x, y) for x in range(x0, x1) for y in range(y0, y1))


ROOM = _box(0, 0, 5, 5)
FIELD = _box(5, 0, 20, 5)
WALL = frozenset((5, y) for y in range(5) if y != 2)


def test_a_small_room_with_one_doorway_is_a_loot_zone() -> None:
    assert choose_loot_zones({0: ROOM, 1: FIELD}, WALL) == {0}


def test_a_room_with_two_doorways_is_not() -> None:
    wall = frozenset((5, y) for y in (1, 2, 3))
    assert choose_loot_zones({0: ROOM, 1: FIELD}, wall) == frozenset()


def test_a_room_in_skip_is_not() -> None:
    assert choose_loot_zones({0: ROOM, 1: FIELD}, WALL, skip={0}) == frozenset()


def test_a_room_beside_water_is_not() -> None:
    ground = [[int(Terrain.WATER) if x == 0 else int(Terrain.GRASS) for x in range(20)]] * 5
    assert choose_loot_zones({0: ROOM, 1: FIELD}, WALL, ground) == frozenset()


def test_a_room_over_the_size_cap_is_not() -> None:
    big = _box(0, 0, 5, 13)
    field = _box(5, 0, 20, 13)
    wall = frozenset((5, y) for y in range(13) if y != 2)
    assert choose_loot_zones({0: big, 1: field}, wall) == frozenset()


def test_the_passage_is_the_open_tiles_on_the_room_side_of_the_doorway() -> None:
    n, tiles = passage(ROOM, ROOM | FIELD, WALL)
    assert (n, tiles) == (1, {(4, 1), (4, 2), (4, 3)})


CANDIDATES = {0: frozenset(range(10)), 1: frozenset(range(10, 16))}


def test_the_draw_takes_the_gates_and_pairs_asked_for_over_both_levels() -> None:
    drawn, monos = draw_loot_zones(CANDIDATES, 4, 2, random.Random(1))
    assert sum(len(z) for z in drawn.values()) == 6
    assert sum(len(z) for z in monos.values()) == 2
    assert all(monos[lvl] <= drawn[lvl] <= CANDIDATES[lvl] for lvl in CANDIDATES)


def test_short_candidates_serve_the_gates_first() -> None:
    drawn, monos = draw_loot_zones({0: frozenset({1, 2})}, 2, 3, random.Random(1))
    assert (drawn[0], monos[0]) == ({1, 2}, frozenset())


def test_the_draw_spreads_over_seeds() -> None:
    draws = {draw_loot_zones(CANDIDATES, 3, 0, random.Random(s))[0][0] for s in range(20)}
    assert len(draws) > 5

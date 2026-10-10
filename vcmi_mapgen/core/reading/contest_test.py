import numpy as np

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import PlacedObject
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.reading.contest import (
    OPEN,
    GoldMine,
    contest,
    enemy_pairs,
    row,
    soonest,
)


def _days(rows: list[list[int]]) -> np.ndarray[tuple[int, int], np.dtype[np.int64]]:
    return np.array(rows, dtype=np.int64)


def test_enemies_are_the_pairs_on_different_teams() -> None:
    assert enemy_pairs(4, (0, 0, 1, 1)) == [(0, 2), (0, 3), (1, 2), (1, 3)]
    assert enemy_pairs(3) == [(0, 1), (0, 2), (1, 2)]


def test_soonest_skips_the_players_who_never_arrive() -> None:
    assert soonest(_days([[5, -1, 3], [-1, -1, -1]])).tolist() == [3, OPEN]


def test_contest_measures_from_the_first_to_its_nearest_enemy() -> None:
    days = _days([[4, 6, 9], [10, 2, 3]])
    assert contest(days, enemy_pairs(3)).tolist() == [2, 1]


def test_an_ally_does_not_contest() -> None:
    days = _days([[4, 5, 9]])
    assert contest(days, [(0, 2), (1, 2)]).tolist() == [5]


def test_contest_is_open_without_an_enemy_or_an_arrival() -> None:
    assert contest(_days([[4, -1], [-1, -1]]), [(0, 1)]).tolist() == [OPEN, OPEN]
    assert contest(row([3, 5]), []).tolist() == [OPEN]


def _gold(catalog: Catalog) -> PlacedObject:
    ident = catalog.mines_by_resource("grass")["goldMine"][0]
    return PlacedObject(10, 12, 0, Purpose.MINE, ident.kind, ident.footprint)


def test_a_gold_mine_near_a_home_misses_the_far_floor(catalog: Catalog) -> None:
    gold = _gold(catalog)
    assert GoldMine(gold, 8, 2).misses(bounded=True) == [
        "gold mine at (10, 12) level 0: 8 days from a home"
    ]
    assert GoldMine(gold, 9, 3).misses(bounded=True) == []


def test_an_uncontested_gold_mine_misses_only_when_bounded(catalog: Catalog) -> None:
    gold = _gold(catalog)
    assert GoldMine(gold, 12, None).misses(bounded=True) == [
        "gold mine at (10, 12) level 0: no enemy arrives"
    ]
    assert GoldMine(gold, 12, 7).misses(bounded=False) == []

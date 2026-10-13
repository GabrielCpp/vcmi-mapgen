"""The corpus spread on literal reading columns."""

from vcmi_mapgen.core.reading.spread import (
    Column,
    Spread,
    columns,
    nearest_columns,
    nearest_players,
)


def test_spread_reads_inclusive_quartiles() -> None:
    assert Spread.of([0.0, 1.0, 2.0, 3.0, 4.0]) == Spread(5, 1.0, 2.0, 3.0)
    assert Spread.of([7.0]) == Spread(1, 7.0, 7.0, 7.0)
    assert Spread.of([]) is None


def test_columns_gather_each_reading_in_first_seen_order() -> None:
    assert columns([{"a": 1.0, "b": 2.0}, {"b": 3.0, "c": 4.0}]) == {
        "a": [1.0],
        "b": [2.0, 3.0],
        "c": [4.0],
    }


def test_nearest_players_keep_the_same_count_when_it_has_enough_maps() -> None:
    assert nearest_players([2, 2, 2, 3, 4], 2, minimum=3) == [2]


def test_nearest_players_pool_the_nearest_counts_until_the_minimum() -> None:
    counts = [1, 2, 3, 3, 4, 4, 4, 6]
    assert nearest_players(counts, 2, minimum=3) == [1, 2, 3]
    assert nearest_players(counts, 5, minimum=3) == [4]
    assert nearest_players(counts, 5, minimum=4) == [4, 6]
    assert nearest_players(counts, 8, minimum=20) == [1, 2, 3, 4, 6]


def test_nearest_columns_pool_each_reading_over_the_maps_that_read_it() -> None:
    maps = [(2, {"a": 1.0}), (2, {"a": 2.0, "b": 5.0}), (3, {"a": 3.0, "b": 6.0})]
    assert nearest_columns(maps, 2, minimum=2) == {
        "a": Column((2,), (1.0, 2.0)),
        "b": Column((2, 3), (5.0, 6.0)),
    }

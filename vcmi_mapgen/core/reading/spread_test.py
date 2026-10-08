"""The corpus spread on literal reading columns."""

from vcmi_mapgen.core.reading.spread import Spread, columns


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

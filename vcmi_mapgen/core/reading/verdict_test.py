"""The corpus spread and the switch rule on literal reading columns."""

from vcmi_mapgen.core.reading.verdict import Spread, columns, decide

CORPUS = {"a": [0.0, 1.0, 2.0, 3.0, 4.0], "b": [10.0, 20.0, 30.0], "c": [5.0, 5.0], "t": [1.0]}


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


def test_closer_on_a_majority_without_a_blocker_switches() -> None:
    verdict = decide(
        CORPUS,
        {"a": [2.0], "b": [21.0], "c": [9.0], "t": [0.0]},
        {"a": [3.0], "b": [25.0], "c": [5.0], "t": [1.0]},
        skip={"t"},
    )
    assert [c.reading for c in verdict.comparisons] == ["a", "b", "c"]
    assert verdict.closer == ("a", "b")
    assert verdict.blockers == ("c",)
    assert not verdict.switch


def test_a_reading_worse_by_less_than_the_iqr_does_not_block() -> None:
    verdict = decide(
        CORPUS,
        {"a": [2.0], "b": [21.0], "c": [5.0]},
        {"a": [3.0], "b": [25.0], "c": [5.0]},
    )
    assert verdict.blockers == ()
    assert verdict.switch


def test_a_tie_on_half_the_readings_is_no_majority() -> None:
    verdict = decide(CORPUS, {"a": [2.0], "b": [20.0]}, {"a": [2.0], "b": [25.0]})
    assert verdict.closer == ("b",)
    assert not verdict.switch


def test_a_reading_one_model_lacks_is_left_out() -> None:
    verdict = decide(CORPUS, {"a": [2.0], "b": []}, {"a": [3.0], "b": [25.0]})
    assert [c.reading for c in verdict.comparisons] == ["a"]

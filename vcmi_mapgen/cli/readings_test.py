"""The readings report on literal reading columns."""

from vcmi_mapgen.cli.readings import table_lines, verdict_lines
from vcmi_mapgen.core.reading.verdict import decide

CORPUS = {"a": [0.0, 1.0, 2.0, 3.0, 4.0]}
MODELS = {"places": {"a": [2.0], "seconds": [1.5]}, "markov": {"a": [3.0]}}


def test_table_lines_show_the_corpus_spread_and_each_model_median() -> None:
    head, a, seconds = table_lines(CORPUS, MODELS)
    assert head.split()[-2:] == ["places", "markov"]
    assert a.split() == ["a", "2.000", "[1.000,", "3.000]", "2.000", "3.000"]
    assert seconds.split() == ["seconds", "-", "1.500", "-"]


def test_verdict_lines_name_the_closer_readings_and_the_blockers() -> None:
    verdict = decide(CORPUS, MODELS["places"], MODELS["markov"])
    first, second = verdict_lines("places", "markov", verdict)
    assert first == "places replaces markov: closer on 1 of 1 readings (a)"
    assert second.endswith("none")

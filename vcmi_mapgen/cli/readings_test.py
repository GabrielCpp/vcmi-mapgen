"""The readings report on literal reading columns."""

from vcmi_mapgen.cli.readings import table_lines

CORPUS = {"a": [0.0, 1.0, 2.0, 3.0, 4.0]}
GENERATED = {"a": [2.0], "seconds": [1.5]}


def test_table_lines_show_the_corpus_spread_and_the_generated_median() -> None:
    head, a, seconds = table_lines(CORPUS, GENERATED)
    assert head.split()[-1] == "generated"
    assert a.split() == ["a", "2.000", "[1.000,", "3.000]", "2.000"]
    assert seconds.split() == ["seconds", "-", "1.500"]

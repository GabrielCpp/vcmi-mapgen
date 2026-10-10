"""The readings report on literal reading columns."""

from vcmi_mapgen.cli.readings import (
    CLOSE_RARE,
    CURVE,
    GOLD_MINES,
    GOLD_NEAR,
    GOLD_OPEN,
    MINES,
    NEAR_COPIES,
    REPEATS,
    SIDE_COPIES,
    TOWN_CURVE,
    TOWNS,
    count_line,
    table_lines,
)

CORPUS = {"a": [0.0, 1.0, 2.0, 3.0, 4.0]}
GENERATED = {"a": [2.0], "seconds": [1.5]}


def test_table_lines_show_the_corpus_spread_and_the_generated_median() -> None:
    head, a, seconds = table_lines(CORPUS, GENERATED)
    assert head.split()[-1] == "generated"
    assert a.split() == ["a", "2.000", "[1.000,", "3.000]", "2.000"]
    assert seconds.split() == ["seconds", "-", "1.500"]


def test_count_line_shows_each_count_beside_its_curve() -> None:
    counts = {MINES: 40.0, CURVE: 50.0, TOWNS: 12.0, TOWN_CURVE: 10.0}
    gold = {GOLD_MINES: 2.0, GOLD_NEAR: 0.0, GOLD_OPEN: 1.0}
    copies = {NEAR_COPIES: 0.1, SIDE_COPIES: 0.03}
    line = count_line(3, {**counts, REPEATS: 1.0, CLOSE_RARE: 0.25, **gold, **copies})
    assert line == (
        "seed 3: 40 resource mines, curve 50.0, ratio 0.80; 12 towns, curve 10.0, ratio 1.20;"
        " 1 ways repeat, close rare share 0.25; 2 gold, 0 near home, 1 uncontested;"
        " copies within 10 0.10, within 6 0.03"
    )

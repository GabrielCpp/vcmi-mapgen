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
    CorpusSide,
    count_line,
    table_lines,
)
from vcmi_mapgen.core.reading.spread import Column

CORPUS = {"a": Column((2, 3), (0.0, 1.0, 2.0, 3.0, 4.0))}
GENERATED = {"a": [2.0], "seconds": [1.5]}
EMPTY: dict[str, float] = {}


def test_table_lines_show_the_corpus_spread_and_the_generated_median() -> None:
    head, a, seconds = table_lines(CORPUS, GENERATED)
    assert head.split()[-3:] == ["players", "maps", "generated"]
    assert a.split() == ["a", "2.000", "[1.000,", "3.000]", "2,3", "5", "2.000"]
    assert seconds.split() == ["seconds", "-", "-", "-", "1.500"]


def test_table_lines_flag_a_generated_median_outside_the_quartiles() -> None:
    _head, low = table_lines(CORPUS, {"a": [0.5]})
    _head, high = table_lines(CORPUS, {"a": [3.5, 4.0]})
    assert low.split()[-1] == "below"
    assert high.split()[-1] == "above"


def test_the_corpus_line_names_the_side_and_the_player_count() -> None:
    assert CorpusSide(72, [(2, EMPTY)] * 5).line(2) == (
        "read 5 corpus maps of side 72; each reading keeps the player counts nearest 2"
        " until 5 maps read it"
    )
    assert CorpusSide(None, []).line(6).startswith("read 0 corpus maps of every side;")


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

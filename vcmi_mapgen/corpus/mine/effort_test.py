from vcmi_mapgen.core.priors.effort import DEFAULT_EDGES, DEFAULT_TOLL, extend_edges
from vcmi_mapgen.corpus.mine.effort import band_edges


def test_edges_sit_at_the_geometric_midpoints_of_the_class_medians() -> None:
    assert band_edges([6.0, 11.0, 16.0, 31.0], []) == (8, 13, 22)


def test_medians_that_do_not_rise_fall_back_to_the_effort_quartiles() -> None:
    assert band_edges([9.0, 9.0, 9.0, 9.0], list(range(1, 10))) == (3, 5, 7)


def test_the_corpus_edges_extended_by_the_toll_are_the_defaults() -> None:
    assert extend_edges(band_edges([6.0, 11.0, 16.0, 31.0], []), DEFAULT_TOLL) == DEFAULT_EDGES

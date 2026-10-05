from vcmi_mapgen.corpus.mine.effort import band_edges


def test_edges_sit_at_the_geometric_midpoints_of_the_class_medians() -> None:
    assert band_edges([6.0, 11.0, 16.0, 31.0], []) == (8, 13, 22)


def test_medians_that_do_not_rise_fall_back_to_the_effort_quartiles() -> None:
    assert band_edges([9.0, 9.0, 9.0, 9.0], list(range(1, 10))) == (3, 5, 7)

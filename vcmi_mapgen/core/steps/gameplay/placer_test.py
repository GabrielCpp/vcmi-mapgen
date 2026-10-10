from vcmi_mapgen.core.steps.gameplay.placer import trim


def test_trim_takes_from_the_family_with_the_most_left_above_its_floor() -> None:
    assert trim({"a": 3, "b": 2}, {"a": 2}, 1) == ({"a": 3, "b": 1}, 0)
    assert trim({"a": 3, "b": 2}, {}, 3) == ({"a": 1, "b": 1}, 0)


def test_trim_counts_what_it_could_not_take() -> None:
    assert trim({"a": 2}, {"a": 1}, 3) == ({"a": 1}, 2)

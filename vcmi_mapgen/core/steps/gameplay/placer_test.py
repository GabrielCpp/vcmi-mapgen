from vcmi_mapgen.core.steps.gameplay.bands import Slot
from vcmi_mapgen.core.steps.gameplay.placer import trim


def test_trim_takes_the_last_slot_of_the_largest_family() -> None:
    slots = [Slot("a", 0), Slot("b", 0), Slot("a", 1), Slot("c", 0)]
    assert trim(slots, {"a", "b"}, 3) == ([Slot("c", 0)], 0)
    assert trim(slots, {"a", "b"}, 1) == ([Slot("a", 0), Slot("b", 0), Slot("c", 0)], 0)


def test_trim_counts_what_it_could_not_take() -> None:
    assert trim([Slot("a"), Slot("c")], {"a"}, 3) == ([Slot("c")], 2)

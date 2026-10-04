"""Palette readings on a small literal place graph."""

from vcmi_mapgen.core.reading.palette import palette_regions, same_by_roles, same_share

DOMINANT = {0: 1, 1: 1, 2: 2, 3: 1, 4: 3}
PAIRS = [(0, 1), (1, 2), (2, 3), (0, 3)]


def test_same_share_counts_pairs_of_one_dominant() -> None:
    assert same_share(DOMINANT, PAIRS) == 0.5
    assert same_share(DOMINANT, []) is None


def test_palette_regions_join_same_dominant_neighbours_and_keep_isolated_places() -> None:
    assert palette_regions(DOMINANT, PAIRS) == 3
    assert palette_regions(DOMINANT, []) == 5


def test_same_by_roles_tallies_sorted_role_pairs() -> None:
    roles = {0: "home", 1: "middle", 2: "middle", 3: "home", 4: "pass"}
    assert same_by_roles(roles, DOMINANT, PAIRS) == {
        "home|home": (1, 1),
        "home|middle": (1, 2),
        "middle|middle": (0, 1),
    }

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Guard, PlacedObject
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.reading.content import UNREACHED, hops, place_content
from vcmi_mapgen.core.reading.value import ARTIFACT_VALUE


def test_hops_count_from_the_nearest_source() -> None:
    dist = hops([(0, 1), (1, 2), (2, 3), (5, 6)], [0, 3])
    assert dist == {0: 0, 3: 0, 1: 1, 2: 1}


def test_a_place_no_source_reaches_has_no_hop() -> None:
    assert 5 not in hops([(0, 1), (5, 6)], [0])


def test_place_content_tallies_rewards_and_guards_per_place(catalog: Catalog) -> None:
    labels = [[0] * 5 + [1] * 5 for _ in range(10)]
    guard = PlacedObject.at(catalog.guard(4), (2, 5), purpose=Purpose.GUARD, payload=Guard())
    art = PlacedObject.at(catalog.random_artifact("major"), (7, 5), purpose=Purpose.REWARD_PICKUP)
    rows = place_content(
        catalog, [guard, art], labels, {0: "home", 1: "treasure", 2: "pass"}, {0: 0, 1: 1}
    )
    home, treasure, passage = rows
    assert (home.role, home.hop, home.area, home.guards, home.value) == ("home", 0, 50, (4,), 0)
    assert (treasure.rewards, treasure.value, treasure.guards) == (1, ARTIFACT_VALUE["major"], ())
    assert (passage.area, passage.hop) == (0, UNREACHED)

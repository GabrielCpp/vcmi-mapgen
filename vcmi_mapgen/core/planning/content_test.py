from collections.abc import Mapping
from dataclasses import dataclass

from vcmi_mapgen.core.planning.content import (
    ContentPlan,
    ContentTable,
    HopContent,
    NoContent,
)
from vcmi_mapgen.core.priors.places import PlaceContent, PlaceStats
from vcmi_mapgen.core.reading.content import UNREACHED
from vcmi_mapgen.core.reading.places import PlaceRole


@dataclass(frozen=True, slots=True)
class _Place:
    role: PlaceRole
    owner: int | None = None


@dataclass(frozen=True, slots=True)
class _Graph:
    places: Mapping[int, _Place]
    passable: frozenset[tuple[int, int]]


def _rows() -> tuple[PlaceContent, ...]:
    return (
        *(PlaceContent("home", 0, 400, 4, 40000, (1, 2)) for _ in range(20)),
        *(PlaceContent("middle", 1, 400, 4, 40000, (3, 3)) for _ in range(20)),
        *(PlaceContent("middle", 2, 400, 4, 60000, (4, 4)) for _ in range(20)),
        PlaceContent("treasure", 2, 100, 2, 50000, (6,) * 10),
    )


def test_a_sparse_cell_reads_between_its_own_rate_and_its_hop_bin() -> None:
    table = ContentTable.of(_rows())
    rich = table.intent("treasure", 2)
    plain = table.intent("middle", 2)
    assert plain.scale < rich.scale < 500 / table.total.value * table.total.tiles
    assert plain.guard < rich.guard < 6


def test_two_unseen_cells_of_one_hop_bin_read_alike() -> None:
    table = ContentTable.of(_rows())
    pocket, passage = table.intent("pocket", 1), table.intent("pass", 1)
    assert (pocket.scale, pocket.guard) == (passage.scale, passage.guard)


def test_value_and_guards_grow_with_hops_from_home() -> None:
    table = ContentTable.of(_rows())
    home, one, two = (table.intent(r, h) for r, h in (("home", 0), ("middle", 1), ("middle", 2)))
    assert home.guard < one.guard < two.guard
    assert one.scale < two.scale


def test_no_content_plans_nothing() -> None:
    graph = _Graph({0: _Place(PlaceRole.HOME, 0)}, frozenset())
    assert NoContent().plan({0: PlaceStats(content=_rows())}, {0: graph}) == ContentPlan()


def test_hop_content_reads_each_place_by_its_role_and_its_hops_from_home() -> None:
    graph = _Graph(
        {
            0: _Place(PlaceRole.HOME, 1),
            1: _Place(PlaceRole.MIDDLE),
            2: _Place(PlaceRole.TREASURE),
            3: _Place(PlaceRole.HOME, 0),
            4: _Place(PlaceRole.POCKET),
        },
        frozenset({(0, 1), (1, 2), (2, 3)}),
    )
    plan = HopContent().plan({0: PlaceStats(content=_rows())}, {0: graph})
    assert plan.homes == ((0, 3), (0, 0))
    assert [plan.intents[0, p].hop for p in range(5)] == [0, 1, 1, 0, UNREACHED]
    assert plan.intents[0, 2].role == "treasure"


def test_hop_content_skips_a_level_without_corpus_content() -> None:
    graph = _Graph({0: _Place(PlaceRole.HOME, 0)}, frozenset())
    plan = HopContent().plan({0: PlaceStats()}, {0: graph})
    assert plan.homes == ((0, 0),)
    assert not plan.intents

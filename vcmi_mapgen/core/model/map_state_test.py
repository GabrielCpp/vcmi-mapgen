import pytest

from vcmi_mapgen.core.model import (
    BORDER,
    CoverIndex,
    Footprint,
    MapState,
    PlacedObject,
    PlacementError,
    Role,
)
from vcmi_mapgen.core.model.purpose import Purpose

_ROLE = {"B": Role.BLOCKING, "X": Role.ENTRANCE, "A": Role.VISIT, "V": Role.OVERLAY}


def _footprint(mask: tuple[str, ...]) -> Footprint:
    """A footprint drawn as rows anchored at the bottom-right cell: B blocking, X entrance,
    A visit, V overlay."""
    h = len(mask)
    cells = tuple(
        (c - (len(row) - 1), r - (h - 1), _ROLE[ch])
        for r, row in enumerate(mask)
        for c, ch in enumerate(row)
    )
    return Footprint(max(len(row) for row in mask), h, cells)


def _obj(x: int, y: int, mask: tuple[str, ...], purpose: str = "") -> PlacedObject:
    return PlacedObject(
        x=x,
        y=y,
        level=0,
        purpose=purpose,
        kind="thing",
        footprint=_footprint(mask),
    )


def test_out_of_map_is_a_blocking_border() -> None:
    state = MapState(size=4)
    for x, y in [(-1, 0), (0, -1), (4, 0), (0, 4)]:
        tile = state.at(0, x, y)
        assert tile is BORDER
        assert tile.border
        assert tile.blocking


def test_tile_reports_covering_roles() -> None:
    mine = _obj(2, 2, ("BB", "XB"))
    state = MapState(size=5, objs=[mine])
    assert state.at(0, 2, 2).blocking
    assert state.at(0, 1, 2).visitable
    approach = state.at(0, 1, 3)
    assert approach.approach
    assert not approach.blocking
    assert state.at(0, 4, 4).free


def test_overlay_over_a_visit_tile_is_refused() -> None:
    mine = _obj(2, 2, ("A",), purpose=Purpose.MINE)
    canopy = _obj(3, 3, ("VV", "VV"))
    state = MapState(size=5)
    with pytest.raises(PlacementError):
        state.add_objs([mine, canopy])


def test_decor_overlay_may_overhang_an_approach_tile() -> None:
    mine = _obj(2, 2, ("X",), purpose=Purpose.MINE)
    canopy = _obj(2, 3, ("V",))
    state = MapState(size=5)
    state.add_objs([mine, canopy])


def test_decor_overlay_may_overhang_an_entrance_tile() -> None:
    mine = _obj(2, 2, ("BB", "BX"), purpose=Purpose.MINE)
    canopy = _obj(2, 2, ("V",), purpose=Purpose.DECORATION)
    index = CoverIndex([canopy])
    assert index.accepts(mine)


def test_gameplay_overlay_over_an_approach_tile_is_refused() -> None:
    mine = _obj(2, 2, ("X",), purpose=Purpose.MINE)
    sprite = _obj(2, 3, ("V",), purpose=Purpose.BANK)
    state = MapState(size=5)
    with pytest.raises(PlacementError):
        state.add_objs([mine, sprite])


def test_guard_may_stand_on_an_approach_tile() -> None:
    mine = _obj(2, 2, ("X",), purpose=Purpose.MINE)
    guard = _obj(2, 3, ("B",), purpose=Purpose.GUARD)
    state = MapState(size=5)
    state.add_objs([mine, guard])
    assert Role.APPROACH in {c.role for c in state.covers_at(0, 2, 3)}


def test_add_objs_keeps_existing_objects_and_appends() -> None:
    mine = _obj(2, 2, ("X",), purpose=Purpose.MINE)
    guard = _obj(2, 3, ("B",), purpose=Purpose.GUARD)
    state = MapState(size=5, objs=[mine])
    state.add_objs([guard])
    assert state.objs == [mine, guard]
    assert state.objs[0] is mine


def test_add_objs_refuses_an_overlay_on_an_existing_visit_tile() -> None:
    mine = _obj(2, 2, ("A",), purpose=Purpose.MINE)
    canopy = _obj(3, 3, ("VV", "VV"))
    state = MapState(size=5, objs=[mine])
    with pytest.raises(PlacementError):
        state.add_objs([canopy])
    assert state.objs == [mine]


def test_add_objs_refuses_a_visit_tile_under_an_existing_overlay() -> None:
    canopy = _obj(3, 3, ("VV", "VV"))
    mine = _obj(2, 2, ("A",), purpose=Purpose.MINE)
    state = MapState(size=5, objs=[canopy])
    with pytest.raises(PlacementError):
        state.add_objs([mine])


def test_cover_index_refuses_an_overlay_on_a_visit_tile() -> None:
    mine = _obj(2, 2, ("A",), purpose=Purpose.MINE)
    canopy = _obj(3, 3, ("VV", "VV"))
    index = CoverIndex([mine])
    assert not index.try_add(canopy)
    assert index.conflicts(canopy)


def test_cover_index_refuses_a_visit_tile_under_an_overlay() -> None:
    canopy = _obj(3, 3, ("VV", "VV"))
    mine = _obj(2, 2, ("A",), purpose=Purpose.MINE)
    index = CoverIndex([canopy])
    assert not index.accepts(mine)


def test_cover_index_accepts_a_guard_on_an_approach_tile() -> None:
    mine = _obj(2, 2, ("X",), purpose=Purpose.MINE)
    guard = _obj(2, 3, ("B",), purpose=Purpose.GUARD)
    index = CoverIndex([mine])
    assert index.try_add(guard)


def test_cover_index_rollback_forgets_objects_and_claims_since_the_mark() -> None:
    mine = _obj(2, 2, ("A",), purpose=Purpose.MINE)
    canopy = _obj(3, 3, ("VV", "VV"))
    index = CoverIndex(claims=[(0, 0)])
    m = index.mark()
    assert index.try_claim(mine, [(2, 2), (0, 0)])
    assert not index.try_add(canopy)
    index.rollback(m)
    assert index.claims == {(0, 0)}
    assert index.try_add(canopy)


def test_cover_index_accepts_an_overlay_over_a_resource_pile() -> None:
    pile = _obj(2, 2, ("A",), purpose=Purpose.RESOURCE_PILE)
    canopy = _obj(3, 3, ("VV", "VV"))
    assert CoverIndex([pile]).try_add(canopy)
    assert CoverIndex([canopy]).try_add(pile)


def test_cover_index_refuses_a_pile_overlay_over_a_mine_visit_tile() -> None:
    mine = _obj(2, 2, ("A",), purpose=Purpose.MINE)
    pile = _obj(3, 2, ("VA",), purpose=Purpose.RESOURCE_PILE)
    assert not CoverIndex([mine]).try_add(pile)


def test_objs_by_level_groups_in_placement_order() -> None:
    state = MapState(size=8)
    a, b, c = _obj(0, 0, ("V",)), _obj(2, 2, ("V",)), _obj(4, 4, ("V",))
    b.level = 1
    state.objs = [a, b, c]
    by_level = state.objs_by_level([0, 1, 2])
    assert by_level == {0: [a, c], 1: [b], 2: []}
    by_level[0].append(b)
    assert state.objs == [a, b, c]

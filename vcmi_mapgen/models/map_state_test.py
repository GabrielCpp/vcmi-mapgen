import pytest

from vcmi_mapgen.models import BORDER, CoverIndex, MapState, PlacedObject, PlacementError, Role


class _NoRules:
    def check(self, _obj: PlacedObject, _cells: object) -> list[str]:
        return []


def _obj(x: int, y: int, mask: tuple[str, ...], purpose: str = "") -> PlacedObject:
    return PlacedObject(
        x=x,
        y=y,
        level=0,
        purpose=purpose,
        type=None,
        subtype=None,
        animation="thing",
        mask=mask,
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
    mine = _obj(2, 2, ("A",), purpose="MINE")
    canopy = _obj(3, 3, ("VV", "VV"))
    state = MapState(size=5)
    with pytest.raises(PlacementError):
        state.add_objs([mine, canopy], _NoRules())


def test_overlay_over_an_approach_tile_is_refused() -> None:
    mine = _obj(2, 2, ("X",), purpose="MINE")
    canopy = _obj(2, 3, ("V",))
    state = MapState(size=5)
    with pytest.raises(PlacementError):
        state.add_objs([mine, canopy], _NoRules())


def test_guard_may_stand_on_an_approach_tile() -> None:
    mine = _obj(2, 2, ("X",), purpose="MINE")
    guard = _obj(2, 3, ("B",), purpose="GUARD")
    state = MapState(size=5)
    state.add_objs([mine, guard], _NoRules())
    assert Role.APPROACH in {c.role for c in state.covers_at(0, 2, 3)}


def test_add_objs_keeps_existing_objects_and_appends() -> None:
    mine = _obj(2, 2, ("X",), purpose="MINE")
    guard = _obj(2, 3, ("B",), purpose="GUARD")
    state = MapState(size=5, objs=[mine])
    state.add_objs([guard], _NoRules())
    assert state.objs == [mine, guard]
    assert state.objs[0] is mine


def test_add_objs_refuses_an_overlay_on_an_existing_visit_tile() -> None:
    mine = _obj(2, 2, ("A",), purpose="MINE")
    canopy = _obj(3, 3, ("VV", "VV"))
    state = MapState(size=5, objs=[mine])
    with pytest.raises(PlacementError):
        state.add_objs([canopy], _NoRules())
    assert state.objs == [mine]


def test_add_objs_refuses_a_visit_tile_under_an_existing_overlay() -> None:
    canopy = _obj(3, 3, ("VV", "VV"))
    mine = _obj(2, 2, ("A",), purpose="MINE")
    state = MapState(size=5, objs=[canopy])
    with pytest.raises(PlacementError):
        state.add_objs([mine], _NoRules())


def test_cover_index_refuses_an_overlay_on_a_visit_tile() -> None:
    mine = _obj(2, 2, ("A",), purpose="MINE")
    canopy = _obj(3, 3, ("VV", "VV"))
    index = CoverIndex([mine])
    assert not index.try_add(canopy)
    assert index.conflicts(canopy)


def test_cover_index_refuses_a_visit_tile_under_an_overlay() -> None:
    canopy = _obj(3, 3, ("VV", "VV"))
    mine = _obj(2, 2, ("A",), purpose="MINE")
    index = CoverIndex([canopy])
    assert not index.accepts(mine)


def test_cover_index_accepts_a_guard_on_an_approach_tile() -> None:
    mine = _obj(2, 2, ("X",), purpose="MINE")
    guard = _obj(2, 3, ("B",), purpose="GUARD")
    index = CoverIndex([mine])
    assert index.try_add(guard)


def test_cover_index_reset_forgets_removed_objects() -> None:
    mine = _obj(2, 2, ("A",), purpose="MINE")
    canopy = _obj(3, 3, ("VV", "VV"))
    index = CoverIndex([mine])
    index.reset([])
    assert index.try_add(canopy)


def test_cover_index_accepts_an_overlay_over_a_resource_pile() -> None:
    pile = _obj(2, 2, ("A",), purpose="RESOURCE_PILE")
    canopy = _obj(3, 3, ("VV", "VV"))
    assert CoverIndex([pile]).try_add(canopy)
    assert CoverIndex([canopy]).try_add(pile)


def test_cover_index_refuses_a_pile_overlay_over_a_mine_visit_tile() -> None:
    mine = _obj(2, 2, ("A",), purpose="MINE")
    pile = _obj(3, 2, ("VA",), purpose="RESOURCE_PILE")
    assert not CoverIndex([mine]).try_add(pile)

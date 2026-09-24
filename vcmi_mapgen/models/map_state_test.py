import pytest

from vcmi_mapgen.models import BORDER, MapState, PlacedObject, PlacementError, Role


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
        state.set_objs([mine, canopy], _NoRules())


def test_overlay_over_an_approach_tile_is_refused() -> None:
    mine = _obj(2, 2, ("X",), purpose="MINE")
    canopy = _obj(2, 3, ("V",))
    state = MapState(size=5)
    with pytest.raises(PlacementError):
        state.set_objs([mine, canopy], _NoRules())


def test_guard_may_stand_on_an_approach_tile() -> None:
    mine = _obj(2, 2, ("X",), purpose="MINE")
    guard = _obj(2, 3, ("B",), purpose="GUARD")
    state = MapState(size=5)
    state.set_objs([mine, guard], _NoRules())
    assert Role.APPROACH in {c.role for c in state.covers_at(0, 2, 3)}

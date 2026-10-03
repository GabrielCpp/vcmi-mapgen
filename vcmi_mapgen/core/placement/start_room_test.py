from vcmi_mapgen.core.model import CoverIndex, Footprint, MapState, PlacedObject, Role
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.placement.start_room import StartRoomRule

_ROLE = {"B": Role.BLOCKING, "X": Role.ENTRANCE, "A": Role.VISIT}
_U_WALL = ("B...B", "B...B", "B...B", "B...B", "BBBBB")


def _footprint(mask: tuple[str, ...]) -> Footprint:
    """A footprint drawn as rows anchored at the bottom-right cell, '.' left uncovered."""
    h = len(mask)
    w = max(len(row) for row in mask)
    cells = tuple(
        (c - (w - 1), r - (h - 1), _ROLE[ch])
        for r, row in enumerate(mask)
        for c, ch in enumerate(row)
        if ch != "."
    )
    return Footprint(w, h, cells)


def _obj(x: int, y: int, mask: tuple[str, ...], purpose: str) -> PlacedObject:
    return PlacedObject(
        x=x, y=y, level=0, purpose=purpose, kind=purpose, footprint=_footprint(mask)
    )


def _start(with_town: bool = True) -> tuple[StartRoomRule, CoverIndex]:
    ground = MapState(size=20, terrain={0: [[Terrain.GRASS] * 20 for _ in range(20)]})
    town = _obj(5, 5, ("BBB", "BXB"), Purpose.TOWN)
    rule = StartRoomRule(ground, 0)
    rule.protect(town)
    return rule, CoverIndex([town] if with_town else [], rules=(rule,))


def test_a_guard_whose_zone_of_control_holds_the_entry_is_refused() -> None:
    _rule, covers = _start()
    assert not covers.accepts(_obj(5, 7, ("A",), Purpose.GUARD))


def test_a_guard_out_of_reach_of_the_entry_is_accepted() -> None:
    _rule, covers = _start()
    assert covers.accepts(_obj(12, 12, ("A",), Purpose.GUARD))


def test_a_wall_that_shuts_the_start_in_a_small_room_is_refused() -> None:
    _rule, covers = _start()
    assert not covers.accepts(_obj(6, 8, _U_WALL, Purpose.MINE))


def test_a_pickup_never_counts_as_a_wall() -> None:
    _rule, covers = _start()
    assert covers.accepts(_obj(6, 8, _U_WALL, Purpose.RESOURCE_PILE))


def test_an_entry_whose_town_is_not_on_the_level_is_not_tested() -> None:
    _rule, covers = _start(with_town=False)
    assert covers.accepts(_obj(5, 7, ("A",), Purpose.GUARD))
    assert covers.accepts(_obj(6, 8, _U_WALL, Purpose.MINE))

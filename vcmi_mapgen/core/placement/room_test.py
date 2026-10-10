from vcmi_mapgen.core.model import CoverIndex, Footprint, PlacedObject, Role
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement.room import RoomRule

_ROOM = {(x, y) for x in range(5) for y in range(3)} - {(2, 0), (2, 2)}


def _obj(x: int, y: int, purpose: str, role: Role = Role.BLOCKING) -> PlacedObject:
    fp = Footprint(1, 1, ((0, 0, role),))
    return PlacedObject(x=x, y=y, level=0, purpose=purpose, kind=purpose, footprint=fp)


def _covers() -> CoverIndex:
    return CoverIndex(rules=(RoomRule([_ROOM]),))


def test_a_rock_in_the_neck_of_a_room_is_refused() -> None:
    assert not _covers().accepts(_obj(2, 1, Purpose.DECORATION))


def test_a_rock_in_a_corner_stands() -> None:
    assert _covers().accepts(_obj(0, 0, Purpose.DECORATION))


def test_a_pickup_in_the_neck_stands() -> None:
    assert _covers().accepts(_obj(2, 1, Purpose.RESOURCE_PILE, Role.VISIT))


def test_a_rock_outside_every_room_stands() -> None:
    assert _covers().accepts(_obj(2, 0, Purpose.DECORATION))

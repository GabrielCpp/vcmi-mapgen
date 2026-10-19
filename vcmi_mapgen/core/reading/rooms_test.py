"""The rooms reading on literal maps: two open rooms joined by a one-tile lane, and two
rooms that touch only at a corner."""

from collections.abc import Iterable

from vcmi_mapgen.core.model import Footprint, MapState, PlacedObject, Role
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.reading.rooms import read_rooms

WIDTH = 15
HEIGHT = 7
LANE_Y = 3


def _square(x: int, y: int, side: int) -> set[tuple[int, int]]:
    return {(x + dx, y + dy) for dx in range(side) for dy in range(side)}


def _state(open_tiles: Iterable[tuple[int, int]], width: int, height: int) -> MapState:
    free = set(open_tiles)
    wall = [
        PlacedObject(x, y, 0, Purpose.DECORATION, "tree", Footprint.one(Role.BLOCKING))
        for y in range(height)
        for x in range(width)
        if (x, y) not in free
    ]
    grid = [[Terrain.GRASS] * width for _ in range(height)]
    return MapState(size=width, terrain={0: grid}, objs=wall)


def test_two_rooms_joined_by_a_lane() -> None:
    lane = {(x, LANE_Y) for x in range(6, 9)}
    state = _state(_square(1, 1, 5) | _square(9, 1, 5) | lane, WIDTH, HEIGHT)
    reading = read_rooms(state, 0)
    assert reading is not None
    walkable = 2 * 25 + len(lane)
    assert reading.room_count == 2
    assert reading.room_median == 25
    assert abs(reading.lane_share - len(lane) / walkable) < 1e-9
    assert abs(reading.room_largest - 25 / walkable) < 1e-9
    assert abs(reading.open_share - 50 / walkable) < 1e-9
    assert abs(reading.blocked_giant - 1.0) < 1e-9


def test_rooms_touching_at_a_corner_stay_two() -> None:
    state = _state(_square(0, 0, 5) | _square(5, 5, 5), 10, 10)
    reading = read_rooms(state, 0)
    assert reading is not None
    assert reading.room_count == 2
    assert reading.lane_share == 0.0
    assert abs(reading.blocked_giant - 0.5) < 1e-9

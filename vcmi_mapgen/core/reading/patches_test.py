"""Patch reading on a small literal grid: an enclosed patch counts with its cover and its
content, a patch in water or below the size floor does not."""

from vcmi_mapgen.core.model import Footprint, MapState, PlacedObject, Role
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.reading.patches import Patch, map_cover, read_patches

G, L, W = Terrain.GRASS, Terrain.LAVA, Terrain.WATER
SIZE = 16


def _obj(t: tuple[int, int], purpose: str, role: Role) -> PlacedObject:
    return PlacedObject(t[0], t[1], 0, purpose, purpose.lower(), Footprint.one(role))


def _state(patch: set[tuple[int, int]], rim: Terrain) -> MapState:
    state = MapState(size=SIZE)
    state.terrain[0] = [[L if (x, y) in patch else rim for x in range(SIZE)] for y in range(SIZE)]
    return state


SQUARE = {(x, y) for x in range(3, 8) for y in range(3, 8)}


def test_an_enclosed_patch_reads_its_cover_and_its_counted_objects() -> None:
    state = _state(SQUARE, G)
    decor = [_obj((x, 3), Purpose.DECORATION, Role.BLOCKING) for x in range(3, 8)]
    state.add_objs([*decor, _obj((5, 5), Purpose.MINE, Role.VISIT)])
    assert read_patches(state, 0) == [Patch(L, 25, 0.2, (Purpose.MINE,))]
    assert map_cover(state, 0) == 5 / (SIZE * SIZE)


def test_a_patch_in_water_or_below_the_floor_is_no_patch() -> None:
    assert read_patches(_state(SQUARE, W), 0) == []
    small = {(x, y) for x in range(3, 6) for y in range(3, 6)}
    assert read_patches(_state(small, G), 0) == []

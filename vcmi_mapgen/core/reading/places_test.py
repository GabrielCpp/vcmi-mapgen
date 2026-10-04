"""Place inference on small literal grids: walls split places, guards gate them, terrain
accents stay inside, and the result never depends on object order."""

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Footprint, MapState, PlacedObject, Role
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.reading.borders import AdjacencyKind
from vcmi_mapgen.core.reading.places import InferredPlaces, PlaceRole, infer_places

WIDTH = 15
HEIGHT = 7
WALL_X = 7
GAP_Y = 3
LEFT_TOWN = (2, 3)
RIGHT_TOWN = (12, 3)
NONE: frozenset[tuple[int, int]] = frozenset()


def _obj(t: tuple[int, int], purpose: str, role: Role) -> PlacedObject:
    return PlacedObject(t[0], t[1], 0, purpose, purpose.lower(), Footprint.one(role))


def _wall(gap: bool) -> list[PlacedObject]:
    return [
        _obj((WALL_X, y), Purpose.DECORATION, Role.BLOCKING)
        for y in range(HEIGHT)
        if not (gap and y == GAP_Y)
    ]


def _towns() -> list[PlacedObject]:
    return [_obj(t, Purpose.TOWN, Role.VISIT) for t in (LEFT_TOWN, RIGHT_TOWN)]


def _state(objs: list[PlacedObject], accent: frozenset[tuple[int, int]]) -> MapState:
    grid = [
        [Terrain.SAND if (x, y) in accent else Terrain.GRASS for x in range(WIDTH)]
        for y in range(HEIGHT)
    ]
    return MapState(size=WIDTH, terrain={0: grid}, objs=objs)


def _infer(
    catalog: Catalog, state: MapState, owners: dict[tuple[int, int, int], int]
) -> InferredPlaces:
    return infer_places(catalog, state, 0, owners)


def test_two_rooms_split_by_a_wall_with_one_gap_are_two_places(catalog: Catalog) -> None:
    places = _infer(catalog, _state(_wall(gap=True) + _towns(), NONE), {(*LEFT_TOWN, 0): 0})
    left = places.labels[LEFT_TOWN[1]][LEFT_TOWN[0]]
    right = places.labels[RIGHT_TOWN[1]][RIGHT_TOWN[0]]
    assert len(places.places) == 2
    assert left != right
    assert all(places.labels[y][x] == left for y in range(HEIGHT) for x in range(WALL_X))
    assert places.places[left].role is PlaceRole.HOME
    assert places.places[left].owner == 0
    assert places.places[right].role is PlaceRole.MIDDLE


def test_a_guard_in_the_gap_gates_the_two_rooms(catalog: Catalog) -> None:
    guard = _obj((WALL_X, GAP_Y), Purpose.GUARD, Role.VISIT)
    places = _infer(catalog, _state([*_wall(gap=True), guard], NONE), {})
    assert len(places.places) == 2
    assert list(places.adjacency.values()) == [AdjacencyKind.GATED]
    (border,) = places.borders.values()
    assert all(c.guarded for c in border.crossings)


def test_a_wall_without_a_gap_closes_the_two_rooms(catalog: Catalog) -> None:
    places = _infer(catalog, _state(_wall(gap=False) + _towns(), NONE), {})
    assert list(places.adjacency.values()) == [AdjacencyKind.CLOSED]


def test_a_terrain_accent_stays_inside_its_place(catalog: Catalog) -> None:
    accent = frozenset((x, y) for x in range(1, 4) for y in range(4, 7))
    places = _infer(catalog, _state(_wall(gap=True) + _towns(), accent), {})
    left = places.labels[LEFT_TOWN[1]][LEFT_TOWN[0]]
    assert {places.labels[y][x] for x, y in accent} == {left}
    assert places.places[left].terrain[Terrain.SAND] == len(accent)
    assert places.places[left].dominant is Terrain.GRASS


def test_water_and_blocked_wall_tiles_follow_the_label_rules(catalog: Catalog) -> None:
    state = _state(_wall(gap=True) + _towns(), NONE)
    state.terrain[0][0][0] = Terrain.WATER
    places = _infer(catalog, state, {})
    assert places.labels[0][0] == -1
    assert places.labels[0][WALL_X] >= 0


def test_inference_ignores_object_order_and_repeats_exactly(catalog: Catalog) -> None:
    objs = [*_wall(gap=True), *_towns(), _obj((4, 1), Purpose.RESOURCE_PILE, Role.VISIT)]
    first = _infer(catalog, _state(objs, NONE), {(*RIGHT_TOWN, 0): 1})
    again = _infer(catalog, _state(list(reversed(objs)), NONE), {(*RIGHT_TOWN, 0): 1})
    assert first == again
    assert first == _infer(catalog, _state(objs, NONE), {(*RIGHT_TOWN, 0): 1})

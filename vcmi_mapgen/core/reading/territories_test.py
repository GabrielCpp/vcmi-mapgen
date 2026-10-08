"""Territories on small literal grids: a monster or a gate in a wall gap splits the land
into two territories joined by one door, a home town owns its territory, a closed room
under the minimum area is no territory, and a monolith links two territories."""

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Footprint, MapState, PlacedObject, Role
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.reading.territories import (
    NONE,
    BarrierKind,
    PlannedTopology,
    Territories,
    disagreements,
    read_territories,
    territory_reading,
)

SIZE = 15
WALL_X = 7
GAP = (WALL_X, 7)
HOME = (2, 7)
LEFT = (1, 1)
RIGHT = (13, 13)
MONSTER = "avwmon3"
GATE = "avxbgt00"
MONOLITH = "avxmn2g0"


def _obj(t: tuple[int, int], purpose: str, role: Role) -> PlacedObject:
    return PlacedObject(t[0], t[1], 0, purpose, purpose.lower(), Footprint.one(role))


def _put(catalog: Catalog, kind: str, x: int, y: int) -> PlacedObject:
    return PlacedObject.at(catalog.identity_of(kind), (x, y), purpose=Purpose.UNKNOWN)


def _wall(gap: bool) -> list[PlacedObject]:
    return [
        _obj((WALL_X, y), Purpose.DECORATION, Role.BLOCKING)
        for y in range(SIZE)
        if not (gap and (WALL_X, y) == GAP)
    ]


def _read(
    catalog: Catalog, objs: list[PlacedObject], owners: dict[tuple[int, int, int], int]
) -> Territories:
    grid = [[Terrain.GRASS] * SIZE for _ in range(SIZE)]
    read = read_territories(catalog, MapState(size=SIZE, terrain={0: grid}, objs=objs), 0, owners)
    assert read is not None
    return read


def _guarded(catalog: Catalog) -> Territories:
    objs = [*_wall(gap=True), _put(catalog, MONSTER, *GAP), _obj(HOME, Purpose.TOWN, Role.VISIT)]
    return _read(catalog, objs, {(*HOME, 0): 0})


def test_a_monster_in_a_wall_gap_splits_two_territories_with_one_door(
    catalog: Catalog,
) -> None:
    read = _guarded(catalog)
    assert len(read.territories) == 2
    assert read.at(LEFT) != read.at(RIGHT)
    assert NONE not in (read.at(LEFT), read.at(RIGHT))
    (door,) = read.doors
    assert door.territories == (0, 1)
    assert door.level == 3
    assert not door.gated
    assert GAP in door.tiles
    assert read.pairs() == {(0, 1): [door]}


def test_a_gate_in_a_wall_gap_is_a_door_of_no_level(catalog: Catalog) -> None:
    read = _read(catalog, [*_wall(gap=True), _put(catalog, GATE, GAP[0] + 1, GAP[1])], {})
    (door,) = read.doors
    assert door.gated
    assert door.level is None
    assert [b.kind for b in door.barriers] == [BarrierKind.GATE]
    assert door.tiles == frozenset({GAP})


def test_the_home_town_owns_its_territory_and_the_other_stays_neutral(
    catalog: Catalog,
) -> None:
    read = _guarded(catalog)
    home, other = read.territories[read.at(LEFT)], read.territories[read.at(RIGHT)]
    assert home.owners == (0,)
    assert home.towns == 1
    assert other.neutral
    assert other.towns == 0


def test_each_place_goes_to_the_territory_that_holds_it(catalog: Catalog) -> None:
    read = _guarded(catalog)
    home, other = read.territories[read.at(LEFT)], read.territories[read.at(RIGHT)]
    assert len(home.zones) == 1
    assert len(other.zones) == 1
    assert home.zones != other.zones


def test_a_closed_room_under_the_minimum_area_is_no_territory(catalog: Catalog) -> None:
    room = [_obj((3, y), Purpose.DECORATION, Role.BLOCKING) for y in range(4)]
    room += [_obj((x, 3), Purpose.DECORATION, Role.BLOCKING) for x in range(3)]
    read = _read(catalog, [*_wall(gap=False), *room], {})
    assert len(read.territories) == 2
    assert read.at(LEFT) == NONE
    assert read.at((5, 10)) != NONE
    assert not read.doors


def test_a_monolith_pair_links_two_territories_without_a_door(catalog: Catalog) -> None:
    objs = [*_wall(gap=False), _put(catalog, MONOLITH, 3, 3), _put(catalog, MONOLITH, 11, 11)]
    read = _read(catalog, objs, {})
    assert not read.doors
    assert read.links == ((0, 1),)


def test_the_reading_splits_doors_by_whether_a_player_owns_a_side(catalog: Catalog) -> None:
    reading = territory_reading(_guarded(catalog))
    assert reading.player_zones == (1,)
    assert reading.neutral_zones == (1,)
    assert reading.pair_doors == (1,)
    assert reading.player_door_levels == (3,)
    assert reading.neutral_door_levels == ()


def _planned(read: Territories, owners: tuple[tuple[int, ...], ...]) -> PlannedTopology:
    return PlannedTopology(read.labels, owners, (GAP,))


def test_a_plan_the_map_follows_has_no_disagreement(catalog: Catalog) -> None:
    read = _guarded(catalog)
    owners = tuple(t.owners for t in read.territories)
    assert disagreements(_planned(read, owners), read) == []


def test_a_plan_names_the_owner_and_door_the_map_lacks(catalog: Catalog) -> None:
    read = _guarded(catalog)
    owners = tuple((1,) if t.neutral else t.owners for t in read.territories)
    planned = PlannedTopology(read.labels, owners, (GAP, (12, 2)))
    other = read.at(RIGHT)
    assert disagreements(planned, read) == [
        f"read {other} owners [], planned {other} owners [1]",
        "planned door at 12,2 reads no door",
    ]


def test_one_planned_territory_over_two_read_ones_is_a_split(catalog: Catalog) -> None:
    read = _guarded(catalog)
    labels = tuple(tuple(0 if v != NONE else NONE for v in row) for row in read.labels)
    planned = PlannedTopology(labels, ((0,),), ())
    found = disagreements(planned, read)
    assert "planned 0 splits into read 0, 1" in found

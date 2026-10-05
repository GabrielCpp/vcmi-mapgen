"""Reliability tests for core.steps.portal.rescue (target reachability, portal rescue)."""

from dataclasses import replace

import pytest

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import (
    CoverIndex,
    Footprint,
    Guard,
    Identity,
    PlacedObject,
    Role,
    Tile,
    Zone,
)
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.steps.portal import rescue as RS

GRASS, ROCK = 2, 9


def _obj(ident: Identity, xy: Tile, purpose: str) -> PlacedObject:
    return PlacedObject.at(ident, xy, purpose=purpose)


def _enclave_fixture() -> tuple[int, list[list[int]], dict[int, Zone], set[Tile], set[Tile]]:
    size = 40
    grid = [[GRASS] * size for _ in range(size)]
    inner = {(x, y) for x in range(31, 37) for y in range(31, 37)}
    for y in range(28, 40):
        for x in range(28, 40):
            if (x, y) not in inner:
                grid[y][x] = ROCK
    ts1 = {(x, y) for x in range(size) for y in range(size) if grid[y][x] == GRASS} - inner
    zones = {
        1: Zone(
            terrain_type=Terrain(GRASS),
            area=len(ts1),
            centroid=(sum(x for x, _ in ts1) / len(ts1), sum(y for _, y in ts1) / len(ts1)),
            tiles=sorted(ts1),
            tiles_set=frozenset(ts1),
        ),
        2: Zone(
            terrain_type=Terrain(GRASS),
            area=len(inner),
            centroid=(33.5, 33.5),
            tiles=sorted(inner),
            tiles_set=frozenset(inner),
        ),
    }
    return size, grid, zones, inner, ts1


def _wall_and_picks(size: int) -> tuple[list[PlacedObject], list[PlacedObject]]:
    veg_wall = [
        _obj(
            Identity("pineTrees", "pineTrees", "pine", Footprint.one(Role.BLOCKING)),
            (6, y),
            "",
        )
        for y in range(size)
    ]
    picks = [
        _obj(
            Identity("resource", "wood", "wood_pile", Footprint.one(Role.VISIT)),
            (2, 5),
            Purpose.RESOURCE_PILE,
        ),
        _obj(
            Identity("resource", "ore", "ore_pile", Footprint.one(Role.VISIT)),
            (10, 5),
            Purpose.RESOURCE_PILE,
        ),
    ]
    return veg_wall, picks


def test_unreachable_targets_reports_vegetation_walls_only() -> None:
    """A vegetation wall between two pickups cuts them off, a gameplay wall makes them
    another island's business, a guard in the way does not cut."""
    size = 12
    grid = [[2] * size for _ in range(size)]
    veg_wall, picks = _wall_and_picks(size)
    targets = [(2, 5), (10, 5)]
    assert RS.unreachable_targets(size, grid, veg_wall + picks, targets) == [(10, 5)]
    assert RS.unreachable_targets(size, grid, picks, targets) == []
    hard_wall = [replace(o, purpose=Purpose.DWELLING) for o in veg_wall]
    assert RS.unreachable_targets(size, grid, hard_wall + picks, targets) == []


def _world(objs: list[PlacedObject]) -> RS.PortalWorld:
    size = 12
    return RS.PortalWorld(
        size,
        {0: [[2] * size for _ in range(size)]},
        {0: {}},
        {0: objs},
        {0: [(2, 5), (10, 5)]},
        {0: []},
        {0: CoverIndex(objs)},
        {},
    )


def test_check_reach_raises_on_a_cut_off_target() -> None:
    veg_wall, picks = _wall_and_picks(12)
    RS.check_reach(_world(picks))
    with pytest.raises(ValueError, match="L0 has 1 target"):
        RS.check_reach(_world(veg_wall + picks))


def _rescue(
    catalog: Catalog, priors: Priors, mines: tuple[Tile, ...] = ((31, 31),)
) -> tuple[list[RS.Rescued], RS.PortalWorld, list[Tile]]:
    size, grid, zones, _inner, _ts1 = _enclave_fixture()
    mine = Identity("mine", "s", "X", Footprint.one(Role.VISIT))
    objs = {
        0: [
            _obj(Identity("town", "s", "X", Footprint.one(Role.VISIT)), (5, 5), Purpose.TOWN),
            *(_obj(mine, xy, Purpose.MINE) for xy in mines),
        ]
    }
    targets = {0: [(5, 6)]}
    world = RS.PortalWorld(
        size,
        {0: grid},
        {0: zones},
        objs,
        targets,
        {0: []},
        {0: CoverIndex(objs[0])},
        priors.gameplay[0],
    )
    rescued = RS.rescue_unreachable_zones(catalog, world, RS.Departure((0, (5, 5))), seed=3)
    return rescued, world, targets[0]


def test_portal_rescue_bridges_an_enclave(catalog: Catalog, priors: Priors) -> None:
    """A rock-enclosed zone gets a same-subtype two-way monolith pair: the far end inside,
    the near end in the reachable host zone with a hostile guard beside it."""
    size, grid, _zones, inner, ts1 = _enclave_fixture()
    rescued, world, _targets = _rescue(catalog, priors)
    objs = world.objs_by_level[0]
    assert len(rescued) == 1 and rescued[0].record.zid == 2
    assert rescued[0].entry in inner
    mono = [o for o in objs if catalog.identity_of(o.kind).type == "monolithTwoWay"]
    subs = {catalog.identity_of(o.kind).subtype for o in mono}
    assert len(mono) == 2 and len(subs) == 1, "a same-subtype two-way pair"
    far = [o for o in mono if (o.x, o.y) in inner]
    near = [o for o in mono if (o.x, o.y) in ts1]
    assert len(far) == 1 and len(near) == 1, "one end inside, one end in the host zone"
    nx, ny = near[0].x, near[0].y
    guards = [
        o for o in objs if o.purpose == Purpose.GUARD and max(abs(o.x - nx), abs(o.y - ny)) == 1
    ]
    assert guards and guards[0].payload == Guard()

    again, world2, _ = _rescue(catalog, priors)
    assert again == rescued and world2.objs_by_level[0] == objs

    assert RS.unreachable_targets(size, grid, objs, [(5, 6), (nx, ny)]) == [], (
        "the reachable-side portal end must be walkable from the start"
    )


def test_a_crowded_enclave_still_gets_its_portal(catalog: Catalog, priors: Priors) -> None:
    _size, _grid, _zones, inner, _ts1 = _enclave_fixture()
    rescued, world, _targets = _rescue(catalog, priors, ((32, 32), (35, 35), (32, 35), (35, 32)))
    assert len(rescued) == 1 and rescued[0].entry in inner
    mono = [
        o for o in world.objs_by_level[0] if catalog.identity_of(o.kind).type == "monolithTwoWay"
    ]
    assert len([o for o in mono if (o.x, o.y) in inner]) == 1


def test_a_priced_zone_is_left_to_its_price(catalog: Catalog, priors: Priors) -> None:
    size, grid, zones, _inner, _ts1 = _enclave_fixture()
    objs: dict[int, list[PlacedObject]] = {0: []}
    world = RS.PortalWorld(
        size, {0: grid}, {0: zones}, objs, {0: []}, {0: []}, {0: CoverIndex([])}, priors.gameplay[0]
    )
    departure = RS.Departure((0, (5, 5)), priced={(0, 2)})
    found = RS.rescue_unreachable_zones(catalog, world, departure, seed=3)
    assert found == [] and objs[0] == []

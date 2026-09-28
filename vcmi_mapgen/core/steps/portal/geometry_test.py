"""Reliability tests for steps.portal.geometry (target reachability, portal rescue)."""

from dataclasses import replace

from vcmi_mapgen.core.model import Identity, PlacedObject, Tile, Zone
from vcmi_mapgen.core.steps.portal import geometry as GEO

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
            terrain_type=GRASS,
            area=len(ts1),
            centroid=(sum(x for x, _ in ts1) / len(ts1), sum(y for _, y in ts1) / len(ts1)),
            tiles=sorted(ts1),
            tiles_set=frozenset(ts1),
        ),
        2: Zone(
            terrain_type=GRASS,
            area=len(inner),
            centroid=(33.5, 33.5),
            tiles=sorted(inner),
            tiles_set=frozenset(inner),
        ),
    }
    return size, grid, zones, inner, ts1


def test_unreachable_targets_reports_vegetation_walls_only() -> None:
    """A vegetation wall between two pickups cuts them off, a gameplay wall makes them
    another island's business, a guard in the way does not cut."""
    size = 12
    grid = [[2] * size for _ in range(size)]
    veg_wall = [
        _obj(Identity("pineTrees", "pineTrees", "avlpn0", ("B",)), (6, y), "") for y in range(size)
    ]
    picks = [
        _obj(Identity("resource", "wood", "avtwood0", ("A",)), (2, 5), "RESOURCE_PILE"),
        _obj(Identity("resource", "ore", "avtore0", ("A",)), (10, 5), "RESOURCE_PILE"),
    ]
    targets = [(2, 5), (10, 5)]
    assert GEO.unreachable_targets(size, grid, veg_wall + picks, targets) == [(10, 5)]
    assert GEO.unreachable_targets(size, grid, picks, targets) == []
    hard_wall = [replace(o, purpose="DWELLING") for o in veg_wall]
    assert GEO.unreachable_targets(size, grid, hard_wall + picks, targets) == []


def test_portal_reward_zone() -> None:
    """A rock-enclosed zone becomes a SPECIAL REWARD zone: a same-subtype two-way monolith
    pair bridges it (far end inside, near end in the reachable host zone with a hostile
    guard adjacent), cache-tagged loot fills it, and traverse counts it reachable."""
    size, grid, zones, inner, ts1 = _enclave_fixture()

    no_gates: set[Tile] = set()

    def run() -> tuple[int, list[PlacedObject], list[Tile]]:
        objs = {
            0: [
                _obj(Identity("town", "s", "X", ("A",)), (5, 5), "TOWN"),
                _obj(Identity("mine", "s", "X", ("A",)), (31, 31), "MINE"),
            ]
        }
        targets = {0: [(5, 6)]}
        n = GEO.rescue_unreachable_zones(
            GEO.PortalWorld(size, {0: grid}, {0: zones}, objs, targets, {0: []}),
            start=(0, (5, 5)),
            gate_xy=no_gates,
            seed=3,
        )
        return n, objs[0], targets[0]

    n, objs, targets = run()
    assert n == 1, "the enclave must be rescued by exactly one portal pair"
    mono = [o for o in objs if o.type == "monolithTwoWay"]
    assert len(mono) == 2 and mono[0].subtype == mono[1].subtype, "a same-subtype two-way pair"
    far = [o for o in mono if (o.x, o.y) in inner]
    near = [o for o in mono if (o.x, o.y) in ts1]
    assert len(far) == 1 and len(near) == 1, "one end inside, one end in the host zone"
    nx, ny = near[0].x, near[0].y
    guards = [o for o in objs if o.purpose == "GUARD" and max(abs(o.x - nx), abs(o.y - ny)) == 1]
    assert guards and guards[0].options == {"character": "hostile"}, (
        "a hostile guard must sit adjacent to the reachable-side end"
    )
    loot = [o for o in objs if o.cache]
    assert len(loot) >= 6 and all((o.x, o.y) in inner for o in loot), (
        "the enclave holds a dense cache-tagged hoard"
    )
    assert set(targets) & {(o.x, o.y) for o in loot}, "rewards are named G2 targets"

    n2, objs2, _ = run()
    assert n2 == n and objs2 == objs

    assert GEO.unreachable_targets(size, grid, objs, [(5, 6), (nx, ny)]) == [], (
        "the reachable-side portal end must be walkable from the start"
    )


def test_portal_reward_zone_never_places_an_artifact() -> None:
    """Artifacts (and pandora's box / chests) are pocket/loot-zone only now -- the
    portal-rescue reward hoard must be resource piles alone, never a REWARD_PICKUP
    (which used to draw from RND_ART)."""
    size, grid, zones, _inner, _ts1 = _enclave_fixture()
    no_gates: set[Tile] = set()
    objs = {
        0: [
            _obj(Identity("town", "s", "X", ("A",)), (5, 5), "TOWN"),
            _obj(Identity("mine", "s", "X", ("A",)), (31, 31), "MINE"),
        ]
    }
    targets = {0: [(5, 6)]}
    _ = GEO.rescue_unreachable_zones(
        GEO.PortalWorld(size, {0: grid}, {0: zones}, objs, targets, {0: []}),
        start=(0, (5, 5)),
        gate_xy=no_gates,
        seed=3,
    )

    loot = [o for o in objs[0] if o.cache]
    assert len(loot) >= 6, "fixture assumption broke: expected a dense reward hoard"
    assert not any(o.purpose == "REWARD_PICKUP" for o in loot), (
        "a portal-rescued zone's hoard must be resources only, never an artifact"
    )

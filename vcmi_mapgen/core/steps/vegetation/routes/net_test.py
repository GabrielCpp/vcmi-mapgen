"""The route net on literal rooms: waypoints at the ways in and over the room, straight
routes where the room allows, and a net no pair of waypoints walks far past the line."""

from vcmi_mapgen.core.grid.reach import STEPS8, distances
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.steps.vegetation.routes.net import STRETCH, route, route_net, waypoints

SIDE = 30


def _room() -> set[Tile]:
    return {(x, y) for x in range(SIDE) for y in range(SIDE)}


def test_each_way_in_gets_one_waypoint_and_the_room_is_covered() -> None:
    ways_in = {(0, 4), (0, 5), (0, 6), (SIDE - 1, 20), (SIDE - 1, 21)}
    nodes = waypoints(ways_in, _room(), 8)
    assert nodes[:2] == [(0, 5), (SIDE - 1, 20)]
    assert all(min(max(abs(x - a), abs(y - b)) for a, b in nodes) < 8 for x, y in _room())


def test_a_route_runs_straight_through_open_ground_and_bends_round_a_wall() -> None:
    assert route((2, 2), (20, 11), _room()) == sorted(
        route((2, 2), (20, 11), _room()), key=lambda t: t[0]
    )
    assert len(route((2, 2), (20, 11), _room())) == 19
    wall = {(15, y) for y in range(SIDE - 1)}
    bent = route((5, 5), (25, 5), _room() - wall)
    assert bent[0] == (5, 5) and bent[-1] == (25, 5)
    assert not set(bent) & wall


def test_no_pair_of_waypoints_walks_the_net_far_past_the_line() -> None:
    nodes = [(2, 2), (2, 15), (2, 27), (15, 27), (27, 27), (27, 15), (27, 2)]
    net = route_net(nodes, _room())
    for a in nodes:
        steps = distances(net, [a], STEPS8)
        for b in nodes:
            cheb = max(abs(a[0] - b[0]), abs(a[1] - b[1]))
            assert steps[b] <= STRETCH * cheb

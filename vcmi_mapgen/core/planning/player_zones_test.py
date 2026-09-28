"""Reliability tests for the player-zone pick."""

from vcmi_mapgen.core.model import Zone
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.planning.player_zones import select_player_zones


def test_select_player_zones_far_apart() -> None:
    """Player zones must be big AND mutually far apart — never all clustered together."""

    def zone(cx: float, cy: float, area: int) -> Zone:
        return Zone(
            terrain_type=Terrain.GRASS,
            area=area,
            centroid=(cx, cy),
            tiles=[],
            tiles_set=frozenset(),
        )

    zones = {
        0: zone(36, 36, 500),  # big centre
        1: zone(4, 4, 220),
        2: zone(68, 4, 200),
        3: zone(4, 68, 200),
        4: zone(68, 68, 220),
        5: zone(40, 40, 300),  # big but right NEXT to the centre
        6: zone(30, 30, 40),
    }  # too small: never a start
    zones_by_level = {0: zones}
    picks = select_player_zones(zones_by_level, 2)
    assert picks[0] == (0, 0), "first pick is the largest zone"
    assert picks[1][1] in (1, 2, 3, 4), "second pick is a far corner, not the adjacent zone 5"
    picks4 = select_player_zones(zones_by_level, 4)
    zids4 = [zid for _l, zid in picks4]
    assert 6 not in zids4 and 5 not in zids4, "small/adjacent zones lose to far corners"
    cents = [zones[zid].centroid for _l, zid in picks4]
    dmin = min(
        (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 for i, a in enumerate(cents) for b in cents[i + 1 :]
    )
    assert dmin >= 32**2, "chosen starts keep real distance between them"
    assert select_player_zones(zones_by_level, 2) == picks, "selection is deterministic"

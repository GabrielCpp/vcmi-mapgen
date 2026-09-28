"""Reliability tests for the border plan (vegetation) and the border guards (border)."""

from vcmi_mapgen.core.model import Tile, Zone
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.steps.border import border_seal as BS
from vcmi_mapgen.core.steps.placement import guard_spaced
from vcmi_mapgen.core.steps.vegetation.border_plan import BorderPlan, seal_borders
from vcmi_mapgen.kit.topology import plan_entrances

S, GRASS = 20, 2


def _zones() -> tuple[dict[int, Zone], set[Tile], set[Tile]]:
    ts1 = {(x, y) for x in range(10) for y in range(S)}
    ts2 = {(x, y) for x in range(10, S) for y in range(S)}
    zones = {
        1: Zone(
            terrain_type=Terrain(GRASS),
            area=len(ts1),
            centroid=(4.5, 9.5),
            tiles=sorted(ts1),
            tiles_set=frozenset(ts1),
        ),
        2: Zone(
            terrain_type=Terrain(GRASS),
            area=len(ts2),
            centroid=(14.5, 9.5),
            tiles=sorted(ts2),
            tiles_set=frozenset(ts2),
        ),
    }
    return zones, ts1, ts2


def test_border_plan_closes_or_guards() -> None:
    """Every cross-zone 8-adjacent open crossing outside the planned entrance bands is
    either SEALED with a blocking decoration or contested by a back-path GUARD's zone of
    control. An unguardable and unsealable free crossing must not survive."""
    zones, ts1, ts2 = _zones()
    grid = [[GRASS] * S for _ in range(S)]
    plan = plan_entrances(zones)
    bands: set[Tile] = set()
    for ents in plan.values():
        for _r, b, _o in ents:
            bands |= set(b)
    web_pair = {(9, 2), (10, 2)}
    avoid = bands | web_pair

    border_plan = BorderPlan(ts1 | ts2, zones, bands, avoid, frozenset[Tile]())
    plan_objs, sealed = seal_borders(border_plan, [], 3, 0)
    again = seal_borders(border_plan, [], 3, 0)
    assert again == (plan_objs, sealed), "deterministic"
    assert sealed and not (sealed & avoid), "seals never land on protected tiles"

    guards, guard_tiles, n_open = BS.guard_crossings(
        BS.LevelGrid(S, S, grid, zones), BS.CrossingRules(bands, set[Tile]()), plan_objs, 3, 0
    )
    assert guard_tiles & web_pair, "the unsealable web crossing gets a back-path guard"
    assert n_open == 0
    assert all(o.seal and o.options == {"character": "hostile"} for o in guards)
    tiles = sorted(guard_tiles)
    assert all(guard_spaced(t, tiles[i + 1 :]) for i, t in enumerate(tiles))

    open_all = (ts1 | ts2) - sealed

    def zoc(t: Tile) -> bool:
        return any(max(abs(g[0] - t[0]), abs(g[1] - t[1])) <= 1 for g in guard_tiles)

    for t in sorted(open_all):
        for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
            n = (t[0] + dx, t[1] + dy)
            if n not in open_all:
                continue
            if (t in ts1) == (n in ts1):
                continue
            assert t in bands or n in bands or zoc(t) or zoc(n), (
                f"free unguarded crossing survived at {t}->{n}"
            )

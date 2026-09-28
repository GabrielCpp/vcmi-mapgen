"""Tests for the per-level macro grids and their segmentation."""

from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.steps.terrain_gen import macro as MTOPO
from vcmi_mapgen.core.steps.terrain_gen.levels import raw_levels, segment_levels


def test_raw_levels_add_an_underground_with_protected_tunnels() -> None:
    surface = raw_levels(48, 5, MTOPO.MacroOptions(), subterrain=False)
    both = raw_levels(48, 5, MTOPO.MacroOptions(), subterrain=True)
    assert set(surface.grids) == {0}
    assert not surface.tunnel_protect
    assert set(both.grids) == {0, 1}
    assert both.tunnel_protect
    assert both == raw_levels(48, 5, MTOPO.MacroOptions(), subterrain=True)


def test_segment_levels_warns_on_a_sliver_unless_it_holds_a_tunnel() -> None:
    grid = [[Terrain.GRASS] * 10 for _ in range(10)]
    grid[0][0] = grid[0][1] = Terrain.DIRT
    seg, warnings = segment_levels({0: grid, 1: grid}, frozenset({(0, 0)}))
    assert set(seg.zones) == {0, 1}
    assert len(seg.zones[0]) == 2
    assert [w.split(" zone")[0] for w in warnings] == ["  WARNING: level 0"]

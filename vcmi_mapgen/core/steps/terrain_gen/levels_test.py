"""Tests for the per-level macro grids and their segmentation."""

from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.steps.terrain_gen import macro as MTOPO
from vcmi_mapgen.core.steps.terrain_gen.levels import raw_levels, segment_places
from vcmi_mapgen.core.steps.terrain_gen.place_map import flood_places, front_cells
from vcmi_mapgen.core.steps.terrain_gen.result import PlaceMap


def test_raw_levels_add_an_underground_with_protected_tunnels(priors: Priors) -> None:
    surface = raw_levels(priors.terrain, 48, 5, MTOPO.MacroOptions(), subterrain=False)
    both = raw_levels(priors.terrain, 48, 5, MTOPO.MacroOptions(), subterrain=True)
    assert set(surface.grids) == {0}
    assert not surface.tunnel_protect
    assert set(both.grids) == {0, 1}
    assert both.tunnel_protect
    assert both == raw_levels(priors.terrain, 48, 5, MTOPO.MacroOptions(), subterrain=True)


def test_segment_places_warns_on_a_sliver_unless_it_holds_a_tunnel() -> None:
    grid = [[Terrain.GRASS] * 10 for _ in range(10)]
    grid[0][0] = grid[0][1] = Terrain.DIRT
    places = PlaceMap({0: flood_places(grid), 1: flood_places(grid)})
    seg, warnings = segment_places({0: grid, 1: grid}, places, frozenset({(0, 0)}))
    assert set(seg.zones) == {0, 1}
    assert len(seg.zones[0]) == 2
    assert [w.split(" zone")[0] for w in warnings] == ["  WARNING: level 0"]


def test_front_cells_are_the_tiles_beside_another_place() -> None:
    grid = [[Terrain.GRASS] * 5 + [Terrain.DIRT] * 5 for _ in range(10)]
    fronts = front_cells(flood_places(grid).label)
    assert fronts == frozenset((x, y) for x in (4, 5) for y in range(10))


def test_flood_places_plans_bands_as_wide_as_asked() -> None:
    grid = [[Terrain.GRASS] * 5 + [Terrain.DIRT] * 5 for _ in range(30)]
    narrow = flood_places(grid, 1).passages.entrances
    wide = flood_places(grid).passages.entrances
    assert all(len(e.band) == 1 for es in narrow.values() for e in es)
    assert all(len(e.band) == 3 for es in wide.values() for e in es)

from vcmi_mapgen.core.grid.components import components
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.reading.places import PlaceRole
from vcmi_mapgen.core.steps.terrain_gen.place_map import reconcile_places
from vcmi_mapgen.core.steps.terrain_gen.result import LevelPlaces, PlannedPlace


def test_a_piece_handed_to_a_later_place_leaves_every_place_one_piece() -> None:
    row = [0, 0, 0, 0, 2, 1, 0, 2, 2, 2, 2, 2, 1, 1, 1, 1, 1, 1]
    places = {p: PlannedPlace(PlaceRole.MIDDLE, None, Terrain.GRASS) for p in range(3)}
    grid = [[Terrain.GRASS] * len(row)]

    plan = reconcile_places(grid, LevelPlaces([row], places, frozenset()))

    for p in plan.places:
        tiles = {(x, 0) for x, z in enumerate(plan.label[0]) if z == p}
        assert len(set(components(tiles).values())) == 1, plan.label

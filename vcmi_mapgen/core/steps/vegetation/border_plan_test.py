from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Tile, Zone
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.steps.vegetation.border_plan import BorderPlan, seal_borders


def _zone(ts: set[Tile]) -> Zone:
    return Zone(
        terrain_type=Terrain.GRASS,
        area=len(ts),
        centroid=(0.0, 0.0),
        tiles=sorted(ts),
        tiles_set=frozenset(ts),
    )


def test_the_sealer_never_shuts_a_piece_of_the_web_away(catalog: Catalog) -> None:
    west = {(x, y) for x in range(4) for y in range(3)} - {(2, 0)}
    east = {(x, y) for x in range(4, 8) for y in range(3)} - {(4, 0)}
    web = {(0, 0), (0, 1), (0, 2), (3, 0), (7, 0), (7, 1), (7, 2)}
    plan = BorderPlan(
        land=west | east,
        zones={1: _zone(west), 2: _zone(east)},
        bands=frozenset[Tile](),
        avoid=web | {(4, y) for y in range(3)},
        web=web,
    )
    _objs, sealed = seal_borders(catalog, plan, [], 1, 0)
    assert (3, 1) not in sealed


def test_the_sealer_never_shuts_the_next_zones_land_away(catalog: Catalog) -> None:
    west = {(x, y) for x in range(4) for y in range(3)}
    east = {(4, 1)}
    web = {(x, 1) for x in range(5)}
    plan = BorderPlan(
        land=west | east,
        zones={1: _zone(west), 2: _zone(east)},
        bands=frozenset[Tile](),
        avoid=web - {(3, 1)},
        web=web,
    )
    _objs, sealed = seal_borders(catalog, plan, [], 1, 0)
    assert (3, 1) not in sealed

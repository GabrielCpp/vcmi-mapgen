from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Identity
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.placement.ground import allowed_terrains, solid_tiles, stands


def _grass_only(catalog: Catalog) -> Identity:
    return next(
        i
        for i in catalog.decor("grass", blocking=True, max_cells=1)
        if not catalog.allowed_on(i.kind, Terrain.SAND)
    )


def test_stands_follows_the_tile_terrain(catalog: Catalog) -> None:
    ident = _grass_only(catalog)
    grass = [[Terrain.GRASS] * 4 for _ in range(4)]
    patched = [row[:] for row in grass]
    patched[2][2] = Terrain.SAND
    assert stands(catalog, ident, (2, 2), grass)
    assert not stands(catalog, ident, (2, 2), patched)
    assert stands(catalog, ident, (1, 1), patched)


def test_stands_skips_off_map_cells_and_an_empty_ground(catalog: Catalog) -> None:
    ident = _grass_only(catalog)
    sand = [[Terrain.SAND] * 2 for _ in range(2)]
    assert stands(catalog, ident, (5, 5), sand)
    assert stands(catalog, ident, (0, 0), ())


def test_allowed_terrains_match_the_catalog(catalog: Catalog) -> None:
    ident = _grass_only(catalog)
    land = allowed_terrains(catalog, ident.kind)
    assert Terrain.GRASS in land
    assert Terrain.SAND not in land
    assert solid_tiles(ident.footprint, (3, 3)) == [(3, 3)]

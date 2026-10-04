from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Footprint, MapState, PlacedObject, Role
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.reading.places import infer_places
from vcmi_mapgen.renderers.overlays.place import PlaceOverlay

TILE = 32


def _state() -> MapState:
    grid = [[Terrain.GRASS for _ in range(12)] for _ in range(6)]
    wall = [
        PlacedObject(6, y, 0, Purpose.DECORATION, "wall", Footprint.one(Role.BLOCKING))
        for y in range(6)
        if y != 2
    ]
    towns = [PlacedObject(x, 2, 0, Purpose.TOWN, "town", Footprint.one(Role.VISIT)) for x in (2, 9)]
    return MapState(size=12, terrain={0: grid}, objs=[*wall, *towns])


def test_place_overlay_fills_every_place_and_skips_levels_without_places(catalog: Catalog) -> None:
    state = _state()
    overlay = PlaceOverlay({0: infer_places(catalog, state, 0, {})})
    img = overlay.apply(state, 0)
    assert img.size == (12 * TILE, 6 * TILE)
    alpha = img.getchannel("A")
    left = img.getpixel((1 * TILE + 4, 4 * TILE + 4))
    right = img.getpixel((10 * TILE + 4, 4 * TILE + 4))
    assert alpha.getpixel((1 * TILE + 4, 4 * TILE + 4)) != 0
    assert left != right
    assert overlay.apply(state, 1).getchannel("A").getextrema() == (0, 0)

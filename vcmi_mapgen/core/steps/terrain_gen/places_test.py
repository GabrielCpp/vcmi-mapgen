"""Tests for the place-first terrain model."""

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.reading.paint import read_paint
from vcmi_mapgen.core.reading.places import PlaceRole
from vcmi_mapgen.core.steps.terrain_gen.model import TerrainOptions
from vcmi_mapgen.core.steps.terrain_gen.paint import theta_min
from vcmi_mapgen.core.steps.terrain_gen.places import PlacesTerrain, bridge_pinches
from vcmi_mapgen.core.steps.terrain_gen.streams import stream


def test_the_same_seed_draws_the_same_place_map(catalog: Catalog, priors: Priors) -> None:
    options = TerrainOptions(size=48, players=2)
    first = PlacesTerrain().draw(catalog, priors, 3, options)
    again = PlacesTerrain().draw(catalog, priors, 3, options)
    assert first.places == again.places
    assert first.grids == again.grids


def test_every_place_reads_as_its_dominant_and_every_player_keeps_a_home(
    catalog: Catalog, priors: Priors
) -> None:
    draw = PlacesTerrain().draw(catalog, priors, 2, TerrainOptions(size=48, players=4))
    level = draw.places.levels[0]
    grid = draw.grids[0]
    for y, row in enumerate(level.label):
        for x, z in enumerate(row):
            assert (z >= 0) == Terrain(grid[y][x]).is_land
    dominant = {z: place.dominant for z, place in level.places.items()}
    reading = read_paint(grid, level.label, dominant, level.bands)
    assert min(reading.shares.values()) >= theta_min(priors.places[0])
    assert reading.violations == 0
    owners = sorted(p.owner for p in level.places.values() if p.owner is not None)
    assert owners == [0, 1, 2, 3]
    assert all(p.role == PlaceRole.HOME for p in level.places.values() if p.owner is not None)


def test_a_stream_depends_on_its_seed_and_parts_only() -> None:
    assert stream(5, "layout").random() == stream(5, "layout").random()
    assert stream(5, "layout").random() != stream(5, "places").random()
    assert stream(5, "layout").random() != stream(6, "layout").random()


def test_a_diagonal_land_contact_is_bridged_by_the_land_beside_it() -> None:
    G, S, W = Terrain.GRASS.value, Terrain.SNOW.value, Terrain.WATER.value
    ids = [[G, W, W], [W, S, W], [W, W, S]]
    assert bridge_pinches(ids)
    assert ids == [[G, G, W], [W, S, S], [W, W, S]]
    assert not bridge_pinches(ids)

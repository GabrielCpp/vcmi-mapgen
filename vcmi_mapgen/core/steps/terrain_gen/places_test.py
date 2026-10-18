"""Tests for the place-first terrain model."""

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.priors.territories import TerritoryStats
from vcmi_mapgen.core.reading.paint import read_paint
from vcmi_mapgen.core.reading.places import PlaceRole
from vcmi_mapgen.core.steps.terrain_gen.model import TerrainOptions
from vcmi_mapgen.core.steps.terrain_gen.paint import theta_min
from vcmi_mapgen.core.steps.terrain_gen.place_map import label_adjacency, label_borders
from vcmi_mapgen.core.steps.terrain_gen.places import (
    Front,
    PlacesTerrain,
    bordered,
    bridge_pinches,
    carried,
)
from vcmi_mapgen.core.steps.terrain_gen.result import LevelPlaces, PlannedPlace
from vcmi_mapgen.core.steps.terrain_gen.streams import stream
from vcmi_mapgen.core.steps.terrain_gen.territories import unreached
from vcmi_mapgen.core.steps.terrain_gen.water import TopologyForm


def test_the_same_seed_draws_the_same_place_map(catalog: Catalog, priors: Priors) -> None:
    options = TerrainOptions(size=48, players=2)
    first = PlacesTerrain(TopologyForm()).draw(catalog, priors, 3, options)
    again = PlacesTerrain(TopologyForm()).draw(catalog, priors, 3, options)
    assert first.places == again.places
    assert first.grids == again.grids


def test_every_place_reads_as_its_dominant_and_every_player_keeps_a_home(
    catalog: Catalog, priors: Priors
) -> None:
    draw = PlacesTerrain(TopologyForm()).draw(
        catalog, priors, 2, TerrainOptions(size=48, players=4)
    )
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


def test_every_territory_on_a_home_land_opens_toward_a_home(
    catalog: Catalog, priors: Priors
) -> None:
    for seed in (3, 4):
        draw = PlacesTerrain(TopologyForm()).draw(
            catalog, priors, seed, TerrainOptions(size=72, players=2)
        )
        level = draw.places.levels[0]
        assert len(level.territories.owners) > 2
        assert unreached(level.territories, label_adjacency(level.label)) == []


def _joined(pairs: list[tuple[int, int]], start: int) -> set[int]:
    seen, todo = {start}, [start]
    while todo:
        a = todo.pop()
        for x, y in pairs:
            for here, there in ((x, y), (y, x)):
                if here == a and there not in seen:
                    seen.add(there)
                    todo.append(there)
    return seen


def test_the_underground_is_a_territory_front_without_homes_joined_by_planned_gates(
    catalog: Catalog, priors: Priors
) -> None:
    for seed in (1, 2):
        draw = PlacesTerrain(TopologyForm()).draw(
            catalog, priors, seed, TerrainOptions(size=72, players=2, subterrain=True)
        )
        below = draw.places.levels[1]
        tp = below.territories
        assert len(tp.owners) > 1
        assert all(owner is None for owner in tp.owners)
        doors = [d.territories for d in tp.doors]
        for a, b in label_adjacency(below.label):
            assert tp.zones[b] in _joined(doors, tp.zones[a])
        gates = draw.places.gates
        assert gates
        for level in (0, 1):
            zones = [g.zones[level] for g in gates]
            assert len(set(zones)) == len(zones)
            owners = draw.places.levels[level].territories.zones
            assert [g.territories[level] for g in gates] == [owners[z] for z in zones]


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


def test_carried_moves_a_place_cut_off_from_its_territory_to_its_neighbours() -> None:
    before = [[0, 0, 1, 1, 0]]
    label = [[0, 0, 1, 1, 2]]
    assert carried(label, before, (0, 1)) == (0, 1, 1)
    assert carried([[0, 0, 1, 1, -1]], [[0, 0, 1, 1, -1]], (0, 1)) == (0, 1)


def test_label_borders_count_the_touching_tile_pairs_of_each_label_pair() -> None:
    label = [[0, 0, 1], [0, 2, 1], [-1, 2, 2]]
    assert label_borders(label) == {(0, 1): 1, (0, 2): 2, (1, 2): 2}


def test_bordered_joins_a_neutral_territory_the_grown_places_left_under_the_floor(
    priors: Priors,
) -> None:
    label = [
        [0] * 4 + [1] * 2 + [2] * 4 if y < 5 else [-1] * 4 + [1] * 2 + [2] * 4 for y in range(10)
    ]
    places = {
        0: PlannedPlace(PlaceRole.HOME, 0, Terrain.GRASS),
        1: PlannedPlace(PlaceRole.MIDDLE, None, Terrain.GRASS),
        2: PlannedPlace(PlaceRole.HOME, 1, Terrain.GRASS),
    }
    plan = LevelPlaces(label, places, label_adjacency(label))
    spread = (priors.places[0], TerritoryStats())
    kept = bordered(plan, spread, 2, 1, Front(drawn=(0, 1, 2)))
    assert kept.territories.owners == (0, None, 1)
    merged = bordered(plan, spread, 2, 1, Front(drawn=(0, 1, 2), floor=30))
    assert merged.territories.zones == {0: 0, 1: 1, 2: 1}
    assert merged.territories.owners == (0, 1)

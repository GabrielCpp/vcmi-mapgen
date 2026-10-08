from __future__ import annotations

import argparse

import pytest

from vcmi_mapgen.cli.inspect_map import (
    Loaded,
    RouteAsk,
    ends_of,
    from_corpus,
    from_vmap,
    near_lines,
    parse_end,
    parse_tile,
    route_lines,
    tile_lines,
)
from vcmi_mapgen.cli.inspect_territories import territory_lines
from vcmi_mapgen.cli.settings import Settings
from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState, PlacedObject
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.reading.routes import Spot

SIZE = 8
MONSTER = "avwmon3"
STUMP = "avlstm1"
TOWN = "avcranx0"
TOLL = (0, 3, 5, 8, 12, 18, 28, 45)
CORPUS_MAP = "All for One"


def _put(catalog: Catalog, kind: str, x: int, y: int) -> PlacedObject:
    return PlacedObject.at(catalog.identity_of(kind), (x, y), purpose=Purpose.UNKNOWN)


def _walled(catalog: Catalog) -> Loaded:
    grid = [[Terrain.GRASS] * SIZE for _ in range(SIZE)]
    for x in range(SIZE):
        if x != 4:
            grid[4][x] = Terrain.ROCK
    state = MapState(
        size=SIZE,
        terrain={0: grid},
        objs=[_put(catalog, MONSTER, 4, 4), _put(catalog, STUMP, 1, 1)],
    )
    return Loaded("walled", state, {})


def test_a_tile_beside_a_monster_names_its_guard(catalog: Catalog) -> None:
    lines = tile_lines(catalog, _walled(catalog), Spot(0, 4, 5))
    assert lines[0] == "tile 4,5 level 0 of walled: grass"
    assert "  hero: may stand here" in lines
    assert any(line.startswith("  place ") for line in lines)
    assert any(line.startswith("  guard ") and line.endswith("level 3") for line in lines)


def test_a_tile_under_a_stump_blocks_and_names_the_stump(catalog: Catalog) -> None:
    lines = tile_lines(catalog, _walled(catalog), Spot(0, 1, 1))
    assert "  hero: blocked" in lines
    assert any(line.startswith("  object ") and STUMP in line for line in lines)
    assert "  guard: none" in lines


def test_a_tile_off_the_map_says_so(catalog: Catalog) -> None:
    assert tile_lines(catalog, _walled(catalog), Spot(0, SIZE, 0)) == [
        f"no tile {SIZE},0 on level 0 of walled"
    ]


def test_near_lists_the_nearest_object_first_with_its_mask_and_visit(catalog: Catalog) -> None:
    lines = near_lines(catalog, _walled(catalog), Spot(0, 2, 2), 3)
    assert lines[0] == "2 objects within 3 of 2,2 level 0"
    assert lines[1].startswith("  1: ") and STUMP in lines[1]
    assert lines[2] == "     mask B, visit none"
    assert lines[3].startswith("  1: ") and MONSTER in lines[3]
    assert lines[4] == "     mask oo / oV, visit 4,4"


def test_near_leaves_out_objects_beyond_the_radius(catalog: Catalog) -> None:
    assert near_lines(catalog, _walled(catalog), Spot(0, 7, 7), 1) == [
        "0 objects within 1 of 7,7 level 0"
    ]


def test_a_route_through_the_only_gap_pays_its_monster(catalog: Catalog) -> None:
    lines = route_lines(catalog, _walled(catalog), RouteAsk(((4, 0), (4, 7)), verbose=True), TOLL)
    assert lines[0].startswith("route 4,0 -> 4,7 on walled: ")
    assert "for the strongest guard, level 3, 8 tiles" in lines[0]
    assert lines[1].startswith("  guard ") and lines[1].endswith("level 3 toll 8")
    assert lines[2] == "  tiles " + " ".join(f"4,{y}" for y in range(SIZE))


def test_a_route_on_open_ground_meets_no_guard(catalog: Catalog) -> None:
    lines = route_lines(catalog, _walled(catalog), RouteAsk(((0, 5), (7, 7))), TOLL)
    assert lines[0].endswith("0 for the strongest guard, level 0, 8 tiles")
    assert lines[1] == "  no guard on the way"


def test_a_player_end_stands_for_the_entrance_of_its_town(catalog: Catalog) -> None:
    town = _put(catalog, TOWN, 6, 5)
    loaded = Loaded(
        "towns",
        MapState(size=SIZE, terrain={0: [[Terrain.GRASS] * SIZE] * SIZE}, objs=[town]),
        {(6, 5, 0): 0},
    )
    assert ends_of(loaded, 0, 0) == [Spot(0, 4, 5)]
    with pytest.raises(SystemExit):
        _ = ends_of(loaded, 1, 0)


def test_an_end_is_a_player_or_a_tile() -> None:
    assert parse_end("P1") == 1
    assert parse_end("p0") == 0
    assert parse_end("12,7") == (12, 7)
    with pytest.raises(argparse.ArgumentTypeError):
        _ = parse_tile("12")


def test_a_corpus_name_and_its_vmap_path_load_the_same_map(settings: Settings) -> None:
    by_name = from_corpus(settings, CORPUS_MAP)
    by_path = from_vmap(settings.maps_dir / f"{CORPUS_MAP}.vmap")
    assert by_name.name == by_path.name == CORPUS_MAP
    assert by_name.state.size == by_path.state.size
    assert len(by_name.state.objs) == len(by_path.state.objs)
    assert {0, 1} <= set(by_name.owners.values())


def test_territories_split_at_the_monster_and_draw_its_door(catalog: Catalog) -> None:
    lines = territory_lines(catalog, _walled(catalog), 0)
    assert lines[0] == "2 territories, 1 door and 0 links on level 0 of walled"
    assert lines.count("     door to B: level 3 at 4,4") == 1
    assert lines.count("     door to A: level 3 at 4,4") == 1
    assert lines[-6:] == [
        "AAA!!!AA",
        "####!###",
        "BBB!!!BB",
        "BBBBBBBB",
        "BBBBBBBB",
        "planned: none published",
    ]


def test_territories_of_a_missing_level_say_so(catalog: Catalog) -> None:
    assert territory_lines(catalog, _walled(catalog), 1) == ["no level 1 on walled"]

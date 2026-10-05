import collections

import pytest

from vcmi_mapgen.core.model.road import Road
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.vcmi.tiles import (
    Cell,
    TilerTables,
    decode_tile_string,
    road_mask,
    tile_string,
    tile_strings,
)


def test_tile_string_round_trips_through_decode() -> None:
    cells = [
        Cell(t=2, view=0, m=0),
        Cell(t=8, view=3, m=3),
        Cell(t=2, view=5, m=1, rt=1, rd=2, rm=2),
        Cell(t=2, view=5, m=2, ot=2, od=4, om=1),
        Cell(t=6, view=12, m=0, rt=3, rd=1, ot=1, od=7, rm=3, om=2),
    ]
    for c in cells:
        s = tile_string(c)
        assert decode_tile_string(s) == c, f"round-trip broke for {c} -> {s!r}"


def test_tile_string_writes_the_vcmi_road_then_river_codes() -> None:
    assert tile_string(Cell(t=5, view=50, m=0, ot=3, od=15, om=1)) == "rg50_pc15-"
    assert tile_string(Cell(t=5, view=1, m=0, ot=1, od=2, rt=1, rd=10)) == "rg1_pd2_rw10_"


def test_decode_tile_string_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        _ = decode_tile_string("not-a-tile")


def test_road_mask_sets_one_bit_per_road_neighbour() -> None:
    roads = {(1, 0): 1, (0, 1): 1, (2, 2): 1}
    assert road_mask(roads, 1, 1) == (1 << 1) | (1 << 3) | (1 << 7)


def test_tile_strings_draws_each_road_with_the_frame_of_its_neighbours() -> None:
    straight = collections.Counter({(9, 0): 3})
    tables = TilerTables({}, {}, {}, road_exact={(1 << 3) | (1 << 4): straight})
    grid = [[Terrain.GRASS] * 3 for _ in range(3)]
    roads = {(0, 1): Road.DIRT, (1, 1): Road.GRAVEL, (2, 1): Road.DIRT}
    rows = tile_strings(grid, tables, roads)
    assert decode_tile_string(rows[1][1]).ot == Road.GRAVEL
    assert decode_tile_string(rows[1][1]).od == 9
    assert all("p" not in s[2:] for s in rows[0])


def test_a_hota_tile_decodes_to_its_stand_in() -> None:
    assert decode_tile_string("hl3_").t == Terrain.GRASS
    assert decode_tile_string("ws7|").t == Terrain.ROUGH

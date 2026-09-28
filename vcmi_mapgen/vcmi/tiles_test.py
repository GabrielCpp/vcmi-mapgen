import pytest

from vcmi_mapgen.vcmi.tiles import Cell, decode_tile_string, tile_string


def test_tile_string_round_trips_through_decode() -> None:
    cells = [
        Cell(t=2, view=0, m=0, rt=0, rd=0, ot=0, od=0),  # bare grass
        Cell(t=8, view=3, m=3, rt=0, rd=0, ot=0, od=0),  # water, full mirror
        Cell(t=2, view=5, m=1, rt=1, rd=2, ot=0, od=0),  # river only
        Cell(t=2, view=5, m=2, rt=0, rd=0, ot=2, od=4),  # road only
        Cell(t=6, view=12, m=0, rt=3, rd=1, ot=1, od=7),  # river + road
    ]
    for c in cells:
        s = tile_string(c)
        assert decode_tile_string(s) == c, f"round-trip broke for {c} -> {s!r}"


def test_decode_tile_string_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        _ = decode_tile_string("not-a-tile")

from vcmi_mapgen.core.model import CoverIndex, Footprint, PlacedObject, Role
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement.keep_out import KeepOutRule


def _obj(x: int, y: int, role: Role = Role.BLOCKING) -> PlacedObject:
    fp = Footprint(2, 1, ((-1, 0, Role.OVERLAY), (0, 0, role)))
    return PlacedObject(x=x, y=y, level=0, purpose=Purpose.MINE, kind="mine", footprint=fp)


def _covers() -> CoverIndex:
    return CoverIndex(rules=(KeepOutRule([(5, 5)]),))


def test_an_object_on_a_kept_out_tile_is_refused() -> None:
    assert not _covers().accepts(_obj(5, 5))


def test_an_object_whose_overlay_cell_covers_a_kept_out_tile_is_refused() -> None:
    assert not _covers().accepts(_obj(6, 5))


def test_an_object_beside_the_kept_out_tiles_stands() -> None:
    assert _covers().accepts(_obj(5, 6))

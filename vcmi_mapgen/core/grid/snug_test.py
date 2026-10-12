"""Snug fit by size class on literal sprites."""

from vcmi_mapgen.core.grid.snug import in_field, sided, size_class, snug
from vcmi_mapgen.core.model import Footprint, Role

ONE = Footprint.one(Role.VISIT)
PAIR = Footprint(2, 1, ((-1, 0, Role.BLOCKING), (0, 0, Role.VISIT)))
WIDE = Footprint(
    3,
    2,
    (
        (-2, -1, Role.OVERLAY),
        (-1, -1, Role.BLOCKING),
        (0, -1, Role.BLOCKING),
        (-2, 0, Role.BLOCKING),
        (-1, 0, Role.BLOCKING),
        (0, 0, Role.VISIT),
    ),
)


def test_size_class_counts_the_body_cells() -> None:
    assert [size_class(fp) for fp in (ONE, PAIR, WIDE)] == [1, 2, 3]


def test_a_one_tile_object_sits_in_a_hole_or_a_corner() -> None:
    assert snug(ONE, (5, 5), lambda t: t in {(5, 4), (6, 5), (4, 5)})
    assert snug(ONE, (5, 5), lambda t: t in {(5, 4), (6, 5)})
    assert not snug(ONE, (5, 5), lambda t: t in {(4, 5), (6, 5)})
    assert not snug(ONE, (5, 5), lambda t: t == (4, 4))


def test_a_two_tile_object_is_backed_away_from_its_visit_tile() -> None:
    assert snug(PAIR, (5, 5), lambda t: t == (3, 5))
    assert not snug(PAIR, (5, 5), lambda t: t == (6, 5))


def test_a_larger_object_is_backed_above_its_body() -> None:
    assert snug(WIDE, (5, 5), lambda t: t == (5, 3))
    assert snug(WIDE, (5, 5), lambda t: t == (3, 4))
    assert not snug(WIDE, (5, 5), lambda t: t == (2, 5))
    assert not snug(WIDE, (5, 5), lambda t: t == (6, 5))


def test_one_closed_side_makes_a_sprite_sided() -> None:
    assert sided(ONE, (5, 5), lambda t: t == (5, 6))
    assert sided(PAIR, (5, 5), lambda t: t == (4, 4))
    assert not sided(ONE, (5, 5), lambda t: t == (7, 7))


def test_a_corner_or_a_tile_under_the_sprite_makes_a_sprite_sided() -> None:
    assert sided(PAIR, (5, 5), lambda t: t == (6, 6))
    assert sided(WIDE, (5, 5), lambda t: t == (3, 4))
    assert sided(WIDE, (5, 5), lambda t: t == (2, 3))


def test_a_sprite_in_the_field_touches_no_closed_tile() -> None:
    assert in_field(WIDE, (5, 5), lambda t: t in {(1, 5), (5, 2), (7, 5)})
    assert not in_field(WIDE, (5, 5), lambda t: t == (6, 6))
    assert not in_field(WIDE, (5, 5), lambda t: t == (2, 3))
    assert not in_field(ONE, (5, 5), lambda t: t == (4, 4))

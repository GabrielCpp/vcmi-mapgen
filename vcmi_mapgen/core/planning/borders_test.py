"""Tests for core.planning.borders (the crossings of a zone border)."""

from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.planning.borders import closing_pairs, cross_pairs, deep_pairs, wall_shares


def _strip() -> tuple[set[Tile], dict[Tile, int]]:
    tiles = {(x, 0) for x in range(3)}
    return tiles, {(0, 0): 0, (1, 0): 1, (2, 0): 2}


def test_a_band_only_spares_the_crossing_toward_its_own_zone() -> None:
    tiles, owner = _strip()
    plain, banded = cross_pairs(tiles, owner, {((1, 0), 2)})
    assert banded == [((1, 0), (2, 0))]
    assert plain == [((0, 0), (1, 0))]


def test_closing_pairs_leaves_an_open_border_alone() -> None:
    tiles, owner = _strip()
    plain, _ = cross_pairs(tiles, owner, ())
    assert closing_pairs(plain, owner, {(0, 1)}) == [((1, 0), (2, 0))]


def test_deep_pairs_reach_as_far_as_the_wall_between_their_zones() -> None:
    tiles = {(x, 0) for x in range(6)}
    owner = {(0, 0): 0, (1, 0): 0, (2, 0): 1, (3, 0): 2, (4, 0): 2, (5, 0): 2}
    found = deep_pairs(tiles, owner, {(0, 2): 3})
    assert found == [((0, 0), (3, 0)), ((1, 0), (3, 0)), ((1, 0), (4, 0))]
    assert deep_pairs(tiles, owner, {}) == []


def _row(zones: list[int]) -> dict[Tile, int]:
    return {(x, 0): z for x, z in enumerate(zones)}


def test_wall_shares_split_an_even_wall_between_the_two_zones() -> None:
    owner = _row([0, 0, 0, 0, 0, 1, 1, 1, 1, 1])
    shares = wall_shares(owner, {(0, 1): 4}, ())
    assert shares[0] == {(3, 0), (4, 0)}
    assert shares[1] == {(5, 0), (6, 0)}


def test_wall_shares_round_an_odd_wall_up_for_each_zone() -> None:
    owner = _row([0, 0, 0, 0, 0, 1, 1, 1, 1, 1])
    shares = wall_shares(owner, {(0, 1): 3}, ())
    assert shares[0] == {(3, 0), (4, 0)}
    assert shares[1] == {(5, 0), (6, 0)}


def test_wall_shares_reach_the_full_width_around_an_opening_in_the_other_zone() -> None:
    owner = _row([0, 0, 0, 0, 0, 1, 1, 1, 1, 1])
    shares = wall_shares(owner, {(0, 1): 4}, {(7, 0)})
    assert shares[0] == {(3, 0), (4, 0)}
    assert shares[1] == {(5, 0), (6, 0)}
    shares = wall_shares(owner, {(0, 1): 4}, {(6, 0)})
    assert shares[0] == {(2, 0), (3, 0), (4, 0)}


def test_wall_shares_skip_a_pair_without_a_wall_width() -> None:
    owner = _row([0, 0, 1, 1, 2, 2])
    shares = wall_shares(owner, {(0, 1): 2}, ())
    assert set(shares) == {0, 1}
    assert shares[0] == {(1, 0)}
    assert shares[1] == {(2, 0)}
    assert wall_shares(owner, {}, ()) == {}

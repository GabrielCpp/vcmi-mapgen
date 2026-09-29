import pytest

from vcmi_mapgen.core.grid.pocket_masks import PocketMaskError, parse_masks
from vcmi_mapgen.core.priors.bundle import Priors


def test_parse_masks_keeps_only_distinct_orientations() -> None:
    masks = parse_masks("nook 1\nXXX\nX X\nXGX\n\nalcove\nXXXX\nX  X\nXGXX\n")
    counts = {name: sum(1 for m in masks if m.name == name) for name in ("nook 1", "alcove")}
    assert counts == {"nook 1": 4, "alcove": 8}


def test_parse_masks_offsets_are_relative_to_the_guard() -> None:
    (mask, *_rest) = parse_masks("nook 1\nXXX\nX X\nXGX\n")
    assert mask.free == frozenset({(0, -1)})
    assert mask.walls_by_guard == 4


def test_parse_masks_lets_the_guard_cover_an_open_tile_beside_it() -> None:
    (mask, *_rest) = parse_masks("side open\nXXXX\nX  X\nAGXX\n")
    assert mask.free == frozenset({(0, -1), (1, -1)})
    assert mask.walls_by_guard == 2


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("open\nAAA\nX X\nXGX\n", "not closed off"),
        ("two\nXXXX\nXG X\nXGXX\n", "exactly one"),
        ("apart\nXXXXX\nX XXX\nXXX X\nXGXXX\n", "reachable"),
        ("empty\nXXX\nXGX\nXXX\n", "at least one free"),
        ("ragged\nXXX\nX X\nXG\n", "same width"),
        ("odd\nXXX\nXOX\nXGX\n", "unknown symbols"),
        ("n\nXXX\nX X\nXGX\n\nn\nXXX\nX X\nXGX\n", "duplicate name"),
    ],
)
def test_parse_masks_rejects_a_malformed_drawing(text: str, reason: str) -> None:
    with pytest.raises(PocketMaskError, match=reason):
        _ = parse_masks(text)


def test_shipped_masks_load_with_thirty_three_shapes(priors: Priors) -> None:
    assert len({m.name for m in priors.pocket_masks}) == 33

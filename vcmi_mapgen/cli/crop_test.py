"""The crop subcommand on a synthetic map PNG whose tiles each carry their own colour."""

from pathlib import Path

import pytest
from PIL import Image

from vcmi_mapgen.cli.crop import MARK, crop
from vcmi_mapgen.renderers.sprites import TILE

SIDE = 10


def _tile_colour(x: int, y: int) -> tuple[int, int, int]:
    return (x * 20, y * 20, 100)


def _map_png(tmp_path: Path) -> Path:
    img = Image.new("RGB", (SIDE * TILE, SIDE * TILE))
    for y in range(SIDE):
        for x in range(SIDE):
            img.paste(_tile_colour(x, y), (x * TILE, y * TILE, (x + 1) * TILE, (y + 1) * TILE))
    path = tmp_path / "surface.png"
    img.save(path)
    return path


def test_crop_keeps_the_tiles_around_the_target_and_outlines_it(tmp_path: Path) -> None:
    path = crop(_map_png(tmp_path), (5, 4), 2)
    assert path == tmp_path / "surface_crop_5_4_r2.png"
    with Image.open(path) as img:
        assert img.size == (5 * TILE, 5 * TILE)
        assert img.getpixel((TILE // 2, TILE // 2)) == _tile_colour(3, 2)
        assert img.getpixel((2 * TILE, 2 * TILE)) == MARK
        assert img.getpixel((2 * TILE + TILE // 2, 2 * TILE + TILE // 2)) == _tile_colour(5, 4)


def test_crop_stops_at_the_map_edge(tmp_path: Path) -> None:
    path = crop(_map_png(tmp_path), (1, 8), 3, tmp_path / "edge.png")
    with Image.open(path) as img:
        assert img.size == (5 * TILE, 5 * TILE)
        assert img.getpixel((TILE // 2, TILE // 2)) == _tile_colour(0, 5)


def test_crop_refuses_a_tile_off_the_map(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="off the 10x10 map"):
        _ = crop(_map_png(tmp_path), (SIDE, 0), 2)

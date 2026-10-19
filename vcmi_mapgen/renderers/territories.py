"""The territory view: each tile of a level coloured by the territory of its place."""

import colorsys
from collections.abc import Mapping, Sequence

from PIL import Image, ImageDraw

from vcmi_mapgen.core.grid.segment import ZoneLabel
from vcmi_mapgen.core.model import Tile

PX = 10
WATER = (10, 20, 90)
LINE = (30, 30, 30)
DOOR = (255, 255, 255)
HOME = (0, 0, 0)
GOLDEN = 0.61803398875


def territory_colour(territory: int, strong: bool) -> tuple[int, int, int]:
    """The colour of ``territory``, saturated when a player owns it and pale when neutral."""
    r, g, b = colorsys.hsv_to_rgb(
        (territory * GOLDEN) % 1.0, 0.95 if strong else 0.3, 0.85 if strong else 0.97
    )
    return int(r * 255), int(g * 255), int(b * 255)


def _square(draw: ImageDraw.ImageDraw, tile: Tile, inset: int, fill: tuple[int, int, int]) -> None:
    x, y = tile
    draw.rectangle(
        [x * PX + inset, y * PX + inset, x * PX + PX - 1 - inset, y * PX + PX - 1 - inset],
        fill=fill,
    )


def _borders(draw: ImageDraw.ImageDraw, label: ZoneLabel) -> None:
    n = len(label)
    for y in range(n):
        for x in range(n):
            here = label[y][x]
            if here < 0:
                continue
            if x + 1 < n and label[y][x + 1] >= 0 and label[y][x + 1] != here:
                draw.line([(x + 1) * PX, y * PX, (x + 1) * PX, y * PX + PX], fill=LINE)
            if y + 1 < n and label[y + 1][x] >= 0 and label[y + 1][x] != here:
                draw.line([x * PX, (y + 1) * PX, x * PX + PX, (y + 1) * PX], fill=LINE)


def render_territories(
    label: ZoneLabel,
    territory_of: Mapping[int, int],
    owners: Sequence[int | None],
    doors: Sequence[Tile],
    homes: Sequence[Tile],
) -> Image.Image:
    """One level as an image of ``PX`` pixels per tile. ``label`` reads ``[y][x]`` with -1 off
    land, ``territory_of`` gives the territory of each place and ``owners`` the player of
    each territory, None when neutral. A thin dark line runs along each border between
    places, every tile of ``doors`` is white and every tile of ``homes`` carries a black
    square."""
    n = len(label)
    img = Image.new("RGB", (n * PX, n * PX), WATER)
    draw = ImageDraw.Draw(img)
    for y in range(n):
        for x in range(n):
            territory = territory_of.get(label[y][x])
            if territory is not None:
                _square(draw, (x, y), 0, territory_colour(territory, owners[territory] is not None))
    _borders(draw, label)
    for tile in doors:
        _square(draw, tile, 0, DOOR)
    for tile in homes:
        _square(draw, tile, 2, HOME)
    return img

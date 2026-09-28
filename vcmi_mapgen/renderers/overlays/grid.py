"""GridOverlay — tile grid with coordinate labels, for pointing at a tile on the PNG."""

from __future__ import annotations

from typing import override

from PIL import Image, ImageDraw, ImageFont

from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.renderers.overlays.base import TILE, MapOverlay

_MINOR = (255, 255, 255, 40)
_MAJOR = (255, 255, 255, 150)
_LABEL = (255, 255, 0, 255)
_LABEL_BG = (0, 0, 0, 170)
_FONT_SIZE = 10
_MAJOR_EVERY = 5


class GridOverlay(MapOverlay):
    """Faint line on every tile edge, a bright line every 5 tiles. Every tile in the
    top row carries its x and every tile in the left column its y. Every tile whose x and
    y are both multiples of 5 carries its full "x,y" coordinate."""

    _font: ImageFont.FreeTypeFont | ImageFont.ImageFont

    def __init__(self) -> None:
        self._font = ImageFont.load_default(size=_FONT_SIZE)

    def _label(self, draw: ImageDraw.ImageDraw, px: int, py: int, text: str) -> None:
        left, top, right, bottom = draw.textbbox((px + 1, py + 1), text, font=self._font)
        draw.rectangle([left - 1, top - 1, right + 1, bottom + 1], fill=_LABEL_BG)
        draw.text((px + 1, py + 1), text, fill=_LABEL, font=self._font)

    @override
    def apply(self, state: MapState, level: int) -> Image.Image:
        W, H = self._grid_size(state, level)
        img = self._blank(W, H)
        draw = ImageDraw.Draw(img)
        for x in range(W + 1):
            major = x % _MAJOR_EVERY == 0
            draw.line(
                [(x * TILE, 0), (x * TILE, H * TILE)], fill=_MAJOR if major else _MINOR, width=1
            )
        for y in range(H + 1):
            major = y % _MAJOR_EVERY == 0
            draw.line(
                [(0, y * TILE), (W * TILE, y * TILE)], fill=_MAJOR if major else _MINOR, width=1
            )
        for x in range(W):
            self._label(draw, x * TILE, 0, str(x))
        for y in range(1, H):
            self._label(draw, 0, y * TILE, str(y))
        for y in range(_MAJOR_EVERY, H, _MAJOR_EVERY):
            for x in range(_MAJOR_EVERY, W, _MAJOR_EVERY):
                self._label(draw, x * TILE, y * TILE + TILE // 2, f"{x},{y}")
        return img

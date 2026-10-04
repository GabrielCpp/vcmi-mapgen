"""PlaceOverlay: the inferred place map, one hue per place, its borders, its crossings and
each place's role."""

from __future__ import annotations

import colorsys
from collections.abc import Mapping
from typing import override

from PIL import Image, ImageDraw, ImageFont

from vcmi_mapgen.core.model import MapState, Tile
from vcmi_mapgen.core.reading.borders import AdjacencyKind
from vcmi_mapgen.core.reading.measures import regions
from vcmi_mapgen.core.reading.places import InferredPlaces, Place
from vcmi_mapgen.renderers.overlays.base import TILE, MapOverlay

_FILL_ALPHA = 70
_BORDER = (255, 255, 255, 230)
_CROSSING = {
    AdjacencyKind.GATED: (255, 150, 0, 200),
    AdjacencyKind.OPEN: (0, 230, 90, 200),
    AdjacencyKind.CLOSED: (255, 0, 0, 200),
}
_FONT_SIZE = 22
_STROKE = 2


def _hue(pid: int) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb((pid * 0.618033988749895) % 1.0, 0.8, 0.9)
    return int(r * 255), int(g * 255), int(b * 255)


def _label_tile(tiles: frozenset[Tile]) -> Tile:
    cx = sum(x for x, _ in tiles) / len(tiles)
    cy = sum(y for _, y in tiles) / len(tiles)
    return min(tiles, key=lambda t: ((t[0] - cx) ** 2 + (t[1] - cy) ** 2, t))


def _caption(pid: int, place: Place) -> str:
    owner = "" if place.owner is None else f" P{place.owner}"
    return f"{pid} {place.role.value}{owner}"


def _edge_line(u: Tile, v: Tile) -> tuple[int, int, int, int]:
    if u[0] != v[0]:
        x = max(u[0], v[0]) * TILE
        return x, u[1] * TILE, x, (u[1] + 1) * TILE
    y = max(u[1], v[1]) * TILE
    return u[0] * TILE, y, (u[0] + 1) * TILE, y


class PlaceOverlay(MapOverlay):
    """Draw the places inferred for each level: a flat fill per place, a white line along
    every border, every crossing tile outlined in its adjacency kind's colour, and the
    place id, role and owner at the tile nearest each place's centroid. A level with no
    inferred places draws nothing.

    Args:
        places: level -> the places inferred on it.
    """

    _places: Mapping[int, InferredPlaces]
    _font: ImageFont.FreeTypeFont | ImageFont.ImageFont

    def __init__(self, places: Mapping[int, InferredPlaces]) -> None:
        self._places = places
        self._font = ImageFont.load_default(size=_FONT_SIZE)

    @override
    def apply(self, state: MapState, level: int) -> Image.Image:
        w, h = self._grid_size(state, level)
        img = self._blank(w, h)
        inferred = self._places.get(level)
        if inferred is None or not inferred.places:
            return img
        draw = ImageDraw.Draw(img)
        tiles = regions(inferred)
        for pid, ts in tiles.items():
            fill = (*_hue(pid), _FILL_ALPHA)
            for x, y in ts:
                draw.rectangle([x * TILE, y * TILE, (x + 1) * TILE - 1, (y + 1) * TILE - 1], fill)
        for border in inferred.borders.values():
            for u, v in border.edges:
                draw.line(_edge_line(u, v), fill=_BORDER, width=2)
            for cross in border.crossings:
                for x, y in cross.tiles:
                    box = [x * TILE + 3, y * TILE + 3, (x + 1) * TILE - 4, (y + 1) * TILE - 4]
                    draw.rectangle(box, outline=_CROSSING[border.kind], width=3)
        for pid, ts in tiles.items():
            x, y = _label_tile(ts)
            draw.text(
                (x * TILE + TILE // 2, y * TILE + TILE // 2),
                _caption(pid, inferred.places[pid]),
                fill=(255, 255, 255, 255),
                anchor="mm",
                font=self._font,
                stroke_width=_STROKE,
                stroke_fill=(0, 0, 0, 255),
            )
        return img

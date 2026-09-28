"""TileTypeOverlay — color each tile by terrain type (semi-transparent)."""

from __future__ import annotations

from typing import override

from PIL import Image

from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.kit.render_palette import TERRAIN_RGB
from vcmi_mapgen.renderers.overlays._tiles import terrain_code
from vcmi_mapgen.renderers.overlays.base import TILE, MapOverlay

_ALPHA = 90  # overlay opacity; low enough to keep sprites legible


class TileTypeOverlay(MapOverlay):
    """Tint each tile with its terrain color.

    Useful for visualizing terrain-type boundaries, especially when zone fills
    would be misleading (e.g. mixed-terrain zones).

    Args:
        alpha: overlay opacity 0-255 (default 90 ≈ 35 % opaque).
    """

    _alpha: int

    def __init__(self, alpha: int = _ALPHA) -> None:
        self._alpha = alpha

    @override
    def apply(self, state: MapState, level: int) -> Image.Image:
        surf = state.surfs.get(level) or state.cells.get(level)
        if not surf:
            return Image.new("RGBA", (state.size * TILE, state.size * TILE), (0, 0, 0, 0))
        W, H = len(surf[0]), len(surf)
        img = Image.new("RGBA", (W * TILE, H * TILE), (0, 0, 0, 0))
        px = img.load()
        if px is None:
            raise RuntimeError("image has no pixel access")
        for y, row in enumerate(surf):
            for x, cell in enumerate(row):
                t = terrain_code(cell)
                r, g, b = TERRAIN_RGB[t]
                color = (r, g, b, self._alpha)
                x0, y0 = x * TILE, y * TILE
                for dy in range(TILE):
                    for dx in range(TILE):
                        px[x0 + dx, y0 + dy] = color
        return img

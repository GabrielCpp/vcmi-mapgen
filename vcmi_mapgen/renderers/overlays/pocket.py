"""PocketOverlay — magenta gradient over guard-sealed pocket regions.

Pure rendering: pocket geometry (which tiles form a sealed nook, at what depth) is
disposable analysis computed once by steps.repair.caches.place_pocket_caches, not a
MapState fact (see vcmi_mapgen/models/AGENTS.md) -- this overlay never re-derives it."""
from __future__ import annotations

import colorsys

from PIL import Image, ImageDraw

from vcmi_mapgen.models import MapState
from vcmi_mapgen.renderers.overlays.base import MapOverlay, TILE


class PocketOverlay(MapOverlay):
    """Highlight, in a magenta depth gradient, every pocket tile the pipeline already
    identified. Darker magenta = near the pocket's mouth, lighter = deepest tile.

    Args:
        pockets: level -> {(x, y): normalized_depth in 0..1}, exactly RepairStep's
            ``ctx["pockets"]`` (produced by `steps.repair.caches.place_pocket_caches`).
    """

    def __init__(self, pockets: dict | None = None) -> None:
        self._pockets = pockets or {}

    def apply(self, state: MapState, level: int) -> Image.Image:
        W, H = self._grid_size(state, level)
        img = Image.new("RGBA", (W * TILE, H * TILE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        for (x, y), t in self._pockets.get(level, {}).items():
            if not (0 <= x < W and 0 <= y < H):
                continue
            draw.rectangle(
                [x * TILE, y * TILE, (x + 1) * TILE - 1, (y + 1) * TILE - 1],
                fill=_magenta_color(t),
            )
        return img


def _magenta_color(t: float) -> tuple:
    """t=0 (mouth, darkest) -> t=1 (deepest, lightest). Returns RGBA."""
    v = 0.30 + 0.70 * t
    r, g, b = colorsys.hsv_to_rgb(300 / 360, 0.90, v)
    return (int(r * 255), int(g * 255), int(b * 255), 130)

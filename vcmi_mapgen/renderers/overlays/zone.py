"""ZoneOverlay — flat per-zone colored fill drawn over the base map."""

from __future__ import annotations

import colorsys
from typing import override

from PIL import Image, ImageDraw, ImageFont

from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.renderers.overlays.base import TILE, MapOverlay

_FILL_ALPHA = 55  # zone fill opacity
_LABEL_ALPHA = 255  # zone-id label opacity
_LABEL_FONT_SIZE = 26  # px — legible at the 32px tile scale
_LABEL_STROKE_WIDTH = 2  # px — black outline so the label reads over any zone tint


def _zone_color(zid: int) -> tuple[int, int, int]:
    hue = (zid * 0.618033988749895) % 1.0  # golden-ratio hue spread
    r, g, b = colorsys.hsv_to_rgb(hue, 0.75, 0.85)
    return int(r * 255), int(g * 255), int(b * 255)


class ZoneOverlay(MapOverlay):
    """Draw a flat per-zone colored fill, full coverage, one hue per zone.

    Reads ``state.zones[level]`` which must be populated by ``SegmentStep``.
    If zones are absent (e.g. the state came from vcmi.load.load_map) the overlay is
    a no-op.  Optionally renders zone-id text labels at each zone's centroid.

    ``fill`` and ``labels`` are independent so a caller can composite the fill
    early in an overlay stack and a second, ``fill=False`` label-only instance
    last — the label must survive on top of every other overlay, which a
    single fill+label pass can't guarantee once a later overlay paints over it
    (see ``cli._parse_overlays``).

    Args:
        labels: whether to draw zone-id labels (default True).
        fill: whether to draw the per-zone colored fill (default True).
        fill_alpha: zone fill opacity 0-255 (default 55).
    """

    _labels: bool
    _fill: bool
    _fill_alpha: int
    _font: ImageFont.FreeTypeFont | ImageFont.ImageFont

    def __init__(
        self,
        labels: bool = True,
        fill: bool = True,
        fill_alpha: int = _FILL_ALPHA,
    ) -> None:
        self._labels = labels
        self._fill = fill
        self._fill_alpha = fill_alpha
        self._font = ImageFont.load_default(size=_LABEL_FONT_SIZE)

    @property
    def labels(self) -> bool:
        return self._labels

    @property
    def fill(self) -> bool:
        return self._fill

    @override
    def apply(self, state: MapState, level: int) -> Image.Image:
        zones = state.zones.get(level)
        surf = state.surfs.get(level) or state.cells.get(level)
        W = len(surf[0]) if surf and surf[0] else state.size
        H = len(surf) if surf else state.size
        if not zones:
            return Image.new("RGBA", (W * TILE, H * TILE), (0, 0, 0, 0))

        img = Image.new("RGBA", (W * TILE, H * TILE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        for zid, z in zones.items():
            if self._fill:
                r, g, b = _zone_color(zid)
                fill_c = (r, g, b, self._fill_alpha)

                for tx, ty in z.tiles_set:
                    if not (0 <= tx < W and 0 <= ty < H):
                        continue
                    x0, y0 = tx * TILE, ty * TILE
                    draw.rectangle([x0, y0, x0 + TILE - 1, y0 + TILE - 1], fill=fill_c)

            if self._labels:
                centroid = z.centroid
                px = int(centroid[0]) * TILE + TILE // 2
                py = int(centroid[1]) * TILE + TILE // 2
                draw.text(
                    (px, py),
                    str(zid),
                    fill=(255, 255, 255, _LABEL_ALPHA),
                    anchor="mm",
                    font=self._font,
                    stroke_width=_LABEL_STROKE_WIDTH,
                    stroke_fill=(0, 0, 0, _LABEL_ALPHA),
                )

        return img

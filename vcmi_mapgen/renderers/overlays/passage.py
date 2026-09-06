"""PassageOverlay — the walkable seam between two zones (blue)."""
from __future__ import annotations

from PIL import Image, ImageDraw

from vcmi_mapgen.models import MapState
from vcmi_mapgen.renderers.overlays import _tiles
from vcmi_mapgen.renderers.overlays.base import MapOverlay, TILE

_COLOR = (60, 140, 255, 200)


class PassageOverlay(MapOverlay):
    """Blue: passable tiles that border a passable tile in a DIFFERENT zone --
    the actual walkable seam between two zones.

    Reads ``state.zones[level]`` (populated by ``SegmentStep``); a no-op when
    zones are absent.
    """

    def apply(self, state: MapState, level: int) -> Image.Image:
        surf = state.surfs.get(level) or state.cells.get(level)
        zones = state.zones.get(level)
        if not surf or not zones:
            return self._blank(*self._grid_size(state, level))
        W, H = len(surf[0]), len(surf)

        passable = _tiles.passable_tiles(surf, state.objs, level)
        lookup = _tiles.zone_lookup(zones)
        passages = _tiles.passage_tiles(lookup, passable)

        img = Image.new("RGBA", (W * TILE, H * TILE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        for x, y in passages:
            draw.rectangle([x * TILE, y * TILE, (x + 1) * TILE - 1, (y + 1) * TILE - 1],
                           fill=_COLOR)
        return img

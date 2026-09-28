"""PassageOverlay — the walkable seam between two zones (blue)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import override

from PIL import Image, ImageDraw

from vcmi_mapgen.core.model import MapState, Zone
from vcmi_mapgen.renderers.overlays._tiles import passable_tiles, passage_tiles, zone_lookup
from vcmi_mapgen.renderers.overlays.base import TILE, MapOverlay

_COLOR = (60, 140, 255, 200)


class PassageOverlay(MapOverlay):
    """Blue: passable tiles that border a passable tile in a DIFFERENT zone --
    the actual walkable seam between two zones.

    Reads the ``zones`` it is given, level -> zone id -> zone, as TerrainStep's
    ``Segmentation`` holds them; a no-op when a level has no zones.
    """

    _zones: Mapping[int, Mapping[int, Zone]]

    def __init__(self, zones: Mapping[int, Mapping[int, Zone]] | None = None) -> None:
        self._zones = zones or {}

    @override
    def apply(self, state: MapState, level: int) -> Image.Image:
        surf = state.terrain.get(level)
        zones = self._zones.get(level)
        if not surf or not zones:
            return self._blank(*self._grid_size(state, level))
        W, H = len(surf[0]), len(surf)

        passable = passable_tiles(surf, state.objs, level)
        lookup = zone_lookup(zones)
        passages = passage_tiles(lookup, passable)

        img = Image.new("RGBA", (W * TILE, H * TILE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        for x, y in passages:
            draw.rectangle(
                [x * TILE, y * TILE, (x + 1) * TILE - 1, (y + 1) * TILE - 1], fill=_COLOR
            )
        return img

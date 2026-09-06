"""GuardOverlay — a guard monster's zone of control (red)."""
from __future__ import annotations

from PIL import Image, ImageDraw

from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.models import MapState
from vcmi_mapgen.renderers.overlays._tiles import NB8
from vcmi_mapgen.renderers.overlays.base import MapOverlay, TILE

_COLOR = (220, 50, 50, 160)


class GuardOverlay(MapOverlay):
    """Red: the 3x3 zone of control (interactive cell + its 8 neighbours) of every
    placed guard monster. In H3/VCMI a wandering monster attacks any hero who steps
    onto its interactive tile OR any of its 8 neighbours, so the effective block
    zone is 9 tiles, not the sprite's own footprint."""

    def apply(self, state: MapState, level: int) -> Image.Image:
        W, H = self._grid_size(state, level)
        img = Image.new("RGBA", (W * TILE, H * TILE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        for o in state.objs:
            if o.get("l", 0) != level or o.get("purpose") != "GUARD":
                continue
            mask = o.get("mask") or (o.get("template") or {}).get("mask")
            if not mask:
                continue
            for ax, ay in OR.mask_interactive_cells(mask, o.get("x", 0), o.get("y", 0)):
                for dx, dy in [(0, 0)] + NB8:
                    tx, ty = ax + dx, ay + dy
                    if 0 <= tx < W and 0 <= ty < H:
                        draw.rectangle(
                            [tx * TILE, ty * TILE, (tx + 1) * TILE - 1, (ty + 1) * TILE - 1],
                            fill=_COLOR,
                        )
        return img

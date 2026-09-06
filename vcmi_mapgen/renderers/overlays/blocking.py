"""BlockingOverlay — highlight blocked tiles in semi-transparent red."""
from __future__ import annotations

from PIL import Image, ImageDraw

from vcmi_mapgen.models import MapState
from vcmi_mapgen.renderers.overlays import _tiles
from vcmi_mapgen.renderers.overlays.base import MapOverlay, TILE

_COLOR = (220, 50, 50, 100)   # red, ~40 % opaque
_GATE_COLOR = (255, 160, 0, 120)  # amber for gate-blocked tiles

# tiers=True palette: background clutter / a structure's blocked body / its
# visit tile (a bodyless single-tile visitable -- shrine, sign, event -- shares
# the visit-tile color; it has no body of its own to distinguish).
_BACKGROUND_COLOR = (130, 130, 130, 160)
_STRUCT_BODY_COLOR = (0, 200, 80, 160)
_STRUCT_VISIT_COLOR = (0, 120, 40, 220)


class BlockingOverlay(MapOverlay):
    """Draw a red tint over every tile that is blocked by a placed object.

    Uses the object's ``template.mask`` (the 'B'/'X' cells) anchored at the
    object's ``(x, y)`` position.  Also overlays ``state.gate_blk`` tiles in
    amber when present (subterranean gate ZoC).

    Works with both pipeline-generated states (full mask available) and states
    produced by VmapReader.

    Args:
        tiers: split the blocked-tile tint into three finer categories --
            background clutter (grey), a visitable structure's blocked body
            (light green), and its visit tile (dark green, also used for a
            bodyless single-tile visitable like a shrine or sign) -- instead
            of one flat red tint (default False).
    """

    def __init__(self, tiers: bool = False) -> None:
        self._tiers = tiers

    def apply(self, state: MapState, level: int) -> Image.Image:
        surf = state.surfs.get(level) or state.cells.get(level)
        W = len(surf[0]) if surf and surf[0] else state.size
        H = len(surf) if surf else state.size
        img = Image.new("RGBA", (W * TILE, H * TILE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        if self._tiers:
            background, struct_body, struct_visit, solo_visit = \
                _tiles.classify_objects(state.objs, level)
            for tiles, color in (
                (background, _BACKGROUND_COLOR),
                (struct_body, _STRUCT_BODY_COLOR),
                (struct_visit | solo_visit, _STRUCT_VISIT_COLOR),
            ):
                for tx, ty in tiles:
                    if 0 <= tx < W and 0 <= ty < H:
                        _fill_tile(draw, tx, ty, color)
        else:
            for o in state.objs:
                if o.get("l", 0) != level:
                    continue
                mask = (o.get("template") or {}).get("mask")
                if not mask:
                    continue
                ox, oy = o.get("x", 0), o.get("y", 0)
                for tx, ty, blocking in _iter_mask(mask, ox, oy):
                    if blocking and 0 <= tx < W and 0 <= ty < H:
                        _fill_tile(draw, tx, ty, _COLOR)

        # gate blocked tiles (only in subterrain maps)
        for tx, ty in state.gate_blk.get(level, ()):
            if 0 <= tx < W and 0 <= ty < H:
                _fill_tile(draw, tx, ty, _GATE_COLOR)

        return img


def _iter_mask(mask, x, y):
    hh = len(mask)
    for r, row in enumerate(mask):
        ww = len(row)
        for c, ch in enumerate(row):
            if ch == " ":
                continue
            yield x - (ww - 1 - c), y - (hh - 1 - r), (ch in ("B", "X"))


def _fill_tile(draw, tx, ty, color):
    x0, y0 = tx * TILE, ty * TILE
    draw.rectangle([x0, y0, x0 + TILE - 1, y0 + TILE - 1], fill=color)

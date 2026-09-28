"""BlockingOverlay — highlight blocked tiles in semi-transparent red."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from typing import override

from PIL import Image, ImageDraw

from vcmi_mapgen.core.model import MapState, PlacedObject
from vcmi_mapgen.renderers.overlays._tiles import classify_objects
from vcmi_mapgen.renderers.overlays.base import TILE, MapOverlay

_COLOR = (220, 50, 50, 100)  # red, ~40 % opaque
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

    _tiers: bool

    def __init__(self, tiers: bool = False) -> None:
        self._tiers = tiers

    @override
    def apply(self, state: MapState, level: int) -> Image.Image:
        surf = state.surfs.get(level) or state.cells.get(level)
        W = len(surf[0]) if surf and surf[0] else state.size
        H = len(surf) if surf else state.size
        img = Image.new("RGBA", (W * TILE, H * TILE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        if self._tiers:
            _draw_tiers(draw, state.objs, level, W, H)
        else:
            _draw_flat(draw, state.objs, level, W, H)

        # gate blocked tiles (only in subterrain maps)
        for tx, ty in state.gate_blk.get(level, ()):
            if 0 <= tx < W and 0 <= ty < H:
                _fill_tile(draw, tx, ty, _GATE_COLOR)

        return img


def _draw_tiers(
    draw: ImageDraw.ImageDraw, objs: Iterable[PlacedObject], level: int, W: int, H: int
) -> None:
    background, struct_body, struct_visit, solo_visit = classify_objects(objs, level)
    for tiles, color in (
        (background, _BACKGROUND_COLOR),
        (struct_body, _STRUCT_BODY_COLOR),
        (struct_visit | solo_visit, _STRUCT_VISIT_COLOR),
    ):
        for tx, ty in tiles:
            if 0 <= tx < W and 0 <= ty < H:
                _fill_tile(draw, tx, ty, color)


def _draw_flat(
    draw: ImageDraw.ImageDraw, objs: Iterable[PlacedObject], level: int, W: int, H: int
) -> None:
    for o in objs:
        if o.level != level:
            continue
        mask = o.mask
        if not mask:
            continue
        for tx, ty, blocking in _iter_mask(mask, o.x, o.y):
            if blocking and 0 <= tx < W and 0 <= ty < H:
                _fill_tile(draw, tx, ty, _COLOR)


def _iter_mask(mask: Sequence[str], x: int, y: int) -> Iterator[tuple[int, int, bool]]:
    hh = len(mask)
    for r, row in enumerate(mask):
        ww = len(row)
        for c, ch in enumerate(row):
            if ch == " ":
                continue
            yield x - (ww - 1 - c), y - (hh - 1 - r), (ch in ("B", "X"))


def _fill_tile(
    draw: ImageDraw.ImageDraw, tx: int, ty: int, color: tuple[int, int, int, int]
) -> None:
    x0, y0 = tx * TILE, ty * TILE
    draw.rectangle([x0, y0, x0 + TILE - 1, y0 + TILE - 1], fill=color)

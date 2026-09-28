"""Render a .vmap exactly as the VCMI map editor shows it: real 32x32 terrain tiles
from the H3 sprite LOD, real object sprites composited at their anchor positions,
objects drawn back-to-front (painter's order).

This replaces the dot/blob renders that hid structural problems.

Usage:
  uv run python -m vcmi_mapgen.cli render-sprites out/ZoneGraph-All_for_One-s0.vmap
  uv run python -m vcmi_mapgen.cli render-sprites out/ZoneGraph-All_for_One-s0.vmap \\
      --compare "All for One"
    (side-by-side: generated left, real right re-rendered from the corpus .vmap)
"""

from collections.abc import Sequence
from functools import cache

from PIL import Image, ImageDraw

from vcmi_mapgen.core.model import PlacedObject
from vcmi_mapgen.vcmi.formats.defs import parse_def
from vcmi_mapgen.vcmi.formats.lod import LodIndex

# terrain code (first 2 chars of tile string) -> terrain .def filename
TERR_DEF: dict[str, str] = {
    "dt": "dirttl.def",
    "sa": "sandtl.def",
    "gr": "grastl.def",
    "sn": "snowtl.def",
    "sw": "swmptl.def",
    "rg": "rougtl.def",
    "sb": "subbtl.def",
    "lv": "lavatl.def",
    "wt": "watrtl.def",
    "rc": "rocktl.def",
}
TILE = 32  # pixels per map tile
SPECIAL_PALETTE: dict[int, tuple[int, int, int, int]] = {
    0: (0, 0, 0, 0),
    1: (0, 0, 0, 0),
    4: (0, 0, 0, 0),
    5: (0, 0, 0, 0),
    6: (0, 0, 0, 0),
    7: (0, 0, 0, 0),
}


def get_def(index: LodIndex, name: str) -> list[list[Image.Image]] | None:
    return _load_def(index, name.lower())


@cache
def _load_def(index: LodIndex, key: str) -> list[list[Image.Image]] | None:
    data = index.read(key)
    if data is None:
        return None
    try:
        return parse_def(data)
    except Exception:
        return None


# --------------------------------------------------------------------------- terrain tile decode
def terr_tile_img(index: LodIndex, tile_str: str) -> Image.Image:
    """tile_str e.g. 'dt15_' -> 32x32 RGBA terrain tile image."""
    tc = tile_str[:2]
    rest = tile_str[2:]
    # extract view number (digits before mirror char)
    mir_pos = next((i for i, c in enumerate(rest) if c in "_+-|"), len(rest))
    try:
        view = int(rest[:mir_pos])
    except ValueError:
        view = 0
    mir_char = rest[mir_pos] if mir_pos < len(rest) else "_"
    flip_h = mir_char in ("-", "+")
    flip_v = mir_char in ("|", "+")

    def_name = TERR_DEF.get(tc)
    if def_name is None:
        return Image.new("RGBA", (TILE, TILE), (40, 40, 40, 255))
    groups = get_def(index, def_name)
    if not groups or not groups[0]:
        return Image.new("RGBA", (TILE, TILE), (80, 40, 80, 255))
    frames = groups[0]
    img = frames[view % len(frames)].copy()
    if img.size != (TILE, TILE):
        img = img.resize((TILE, TILE), Image.Resampling.NEAREST)
    if flip_h:
        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if flip_v:
        img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    return img.convert("RGBA")


# --------------------------------------------------------------------------- compositing


def render_map(
    index: LodIndex, surf: Sequence[Sequence[str]], objs: Sequence[PlacedObject], title: str = ""
) -> Image.Image:
    H, W = len(surf), len(surf[0])
    canvas = Image.new("RGB", (W * TILE, H * TILE), (0, 0, 0))

    # 1) terrain tiles
    for y in range(H):
        for x in range(W):
            tile_img = terr_tile_img(index, surf[y][x])
            canvas.paste(tile_img.convert("RGB"), (x * TILE, y * TILE))

    # 2) objects: painter's order = sort by y asc, then by x asc (back-to-front)
    sorted_objs = sorted(objs, key=lambda o: (o.level != 0, o.y, o.x))
    miss = 0
    for o in sorted_objs:
        if o.level != 0:
            continue
        anim = o.kind
        if not anim:
            continue
        groups = get_def(index, anim)
        if not groups or not groups[0]:
            miss += 1
            continue
        sprite = groups[0][0]  # frame 0 of group 0
        sw, sh = sprite.size
        # anchor is bottom-right of the object footprint; sprite is drawn so its
        # bottom-right pixel aligns with the bottom-right of the anchor tile.
        px = (o.x + 1) * TILE - sw
        py = (o.y + 1) * TILE - sh
        canvas.paste(sprite.convert("RGB"), (px, py), sprite.split()[3])
    if miss:
        print(f"  {miss} objects with missing sprites")

    # 3) optional title bar
    if title:
        ImageDraw.Draw(canvas).text((4, 4), title, fill=(255, 255, 255))
    return canvas

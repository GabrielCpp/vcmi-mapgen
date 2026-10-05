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

import io
from collections.abc import Sequence
from functools import cache

from PIL import Image, ImageDraw

from vcmi_mapgen.core.model import JsonValue, PlacedObject
from vcmi_mapgen.core.model.road import Road
from vcmi_mapgen.vcmi.content.archive import ContentArchive
from vcmi_mapgen.vcmi.formats import json_value as jv
from vcmi_mapgen.vcmi.formats.defs import parse_def
from vcmi_mapgen.vcmi.tiles import decode_tile_string

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
    "hl": "hota/highlands/tiles",
    "ws": "hota/wasteland/tiles",
}
ROAD_DEF: dict[Road, str] = {
    Road.DIRT: "dirtrd.def",
    Road.GRAVEL: "gravrd.def",
    Road.COBBLESTONE: "cobbrd.def",
}
DEF_SUFFIX = ".def"
JSON_SUFFIX = ".json"
TILE = 32  # pixels per map tile
SPECIAL_PALETTE: dict[int, tuple[int, int, int, int]] = {
    0: (0, 0, 0, 0),
    1: (0, 0, 0, 0),
    4: (0, 0, 0, 0),
    5: (0, 0, 0, 0),
    6: (0, 0, 0, 0),
    7: (0, 0, 0, 0),
}


def get_def(index: ContentArchive, name: str) -> list[list[Image.Image]] | None:
    return _load_def(index, name.lower())


@cache
def _load_def(index: ContentArchive, key: str) -> list[list[Image.Image]] | None:
    data = index.read(key)
    if data is None:
        return _load_json(index, key)
    try:
        return parse_def(data)
    except Exception:
        return None


def _json_frames(doc: dict[str, JsonValue]) -> list[str]:
    for raw in jv.as_list(doc.get("sequences")):
        seq = jv.as_object(raw)
        if jv.as_int(seq.get("group")) == 0:
            return jv.str_list(seq.get("frames"))
    images = [jv.as_object(i) for i in jv.as_list(doc.get("images"))]
    first = sorted(
        (jv.as_int(i.get("frame")), jv.as_str(i.get("file")))
        for i in images
        if jv.as_int(i.get("group")) == 0
    )
    return [f for _, f in first]


def _load_png(index: ContentArchive, name: str) -> Image.Image | None:
    data = index.read(name)
    if data is None:
        return None
    try:
        return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception:
        return None


def _load_json(index: ContentArchive, key: str) -> list[list[Image.Image]] | None:
    """A VCMI `.json` animation: group 0's `.png` frames under its base path."""
    raw = index.read(f"{key.removesuffix(DEF_SUFFIX)}{JSON_SUFFIX}")
    if raw is None:
        return None
    try:
        doc = jv.as_object(jv.loads_relaxed(raw.decode("utf-8-sig")))
    except Exception:
        return None
    base = jv.as_str(doc.get("basepath"))
    frames = [_load_png(index, f"{base}{f}") for f in _json_frames(doc)]
    found = [f for f in frames if f is not None]
    return [found] if found else None


# --------------------------------------------------------------------------- terrain tile decode
def terr_tile_img(index: ContentArchive, tile_str: str) -> Image.Image:
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


def _flipped(img: Image.Image, flip: int) -> Image.Image:
    if flip & 1:
        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if flip & 2:
        img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    return img


def road_tile_img(index: ContentArchive, tile_str: str) -> Image.Image | None:
    """The road sprite a tile string carries, flipped as it says, or None for no road."""
    cell = decode_tile_string(tile_str)
    if not cell.ot:
        return None
    groups = get_def(index, ROAD_DEF[Road(cell.ot)])
    if not groups or not groups[0]:
        return None
    frames = groups[0]
    return _flipped(frames[cell.od % len(frames)].convert("RGBA"), cell.om)


def _paste_roads(canvas: Image.Image, index: ContentArchive, surf: Sequence[Sequence[str]]) -> None:
    for y, row in enumerate(surf):
        for x, tile_str in enumerate(row):
            img = road_tile_img(index, tile_str)
            if img is not None:
                canvas.paste(img.convert("RGB"), (x * TILE, y * TILE + TILE // 2), img.split()[3])


# --------------------------------------------------------------------------- compositing


def render_map(
    index: ContentArchive,
    surf: Sequence[Sequence[str]],
    objs: Sequence[PlacedObject],
    title: str = "",
) -> Image.Image:
    H, W = len(surf), len(surf[0])
    canvas = Image.new("RGB", (W * TILE, H * TILE), (0, 0, 0))

    # 1) terrain tiles
    for y in range(H):
        for x in range(W):
            tile_img = terr_tile_img(index, surf[y][x])
            canvas.paste(tile_img.convert("RGB"), (x * TILE, y * TILE))
    _paste_roads(canvas, index, surf)

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

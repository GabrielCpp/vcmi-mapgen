"""Render a .vmap exactly as the VCMI map editor shows it: real 32x32 terrain tiles
from the H3 sprite LOD, real object sprites composited at their anchor positions,
objects drawn back-to-front (painter's order).

This replaces the dot/blob renders that hid structural problems.

Usage:
  uv run python -m vcmi_mapgen.renderers.sprites out/ZoneGraph-All_for_One-s0.vmap
  uv run python -m vcmi_mapgen.renderers.sprites out/ZoneGraph-All_for_One-s0.vmap \\
      --compare "All for One"
    (side-by-side: generated left, real right re-rendered from the corpus .vmap)
"""

import argparse
import os
from collections.abc import Sequence

from PIL import Image, ImageDraw

from vcmi_mapgen.core.model import PlacedObject
from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.kit.paths import project_root
from vcmi_mapgen.vcmi.formats import vmap as VM
from vcmi_mapgen.vcmi.formats.defs import parse_def
from vcmi_mapgen.vcmi.formats.lod import lod
from vcmi_mapgen.vcmi.formats.vmap.document import VmapDocument

ROOT = project_root()


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


_def_cache: dict[str, list[list[Image.Image]] | None] = {}


def get_def(name: str) -> list[list[Image.Image]] | None:
    key = name.lower()
    if key in _def_cache:
        return _def_cache[key]
    data = lod().read(key)
    if data is None:
        _def_cache[key] = None
        return None
    try:
        groups: list[list[Image.Image]] | None = parse_def(data)
    except Exception:
        groups = None
    _def_cache[key] = groups
    return groups


# --------------------------------------------------------------------------- terrain tile decode
def terr_tile_img(tile_str: str) -> Image.Image:
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
    groups = get_def(def_name)
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


# --------------------------------------------------------------------------- vmap reader
def _adapt(doc: VmapDocument) -> tuple[list[list[str]], list[PlacedObject]]:
    """A VmapDocument -> the (surf, objs) shape render_map needs (surface terrain +
    each object's l/x/y/type/animation/mask)."""
    surf = doc.terrain[0]
    objs = [
        PlacedObject(
            x=o.x,
            y=o.y,
            level=o.level,
            purpose="",
            type=o.type,
            subtype=None,
            animation=o.animation,
            mask=tuple(o.mask),
        )
        for o in doc.objects
    ]
    return surf, objs


def read_vmap(path: str) -> tuple[list[list[str]], list[PlacedObject]]:
    return _adapt(VM.read(path))


def read_real(name: str) -> tuple[list[list[str]], list[PlacedObject]]:
    """Load the corpus map's own .vmap (full tile view/mirror data) + objects with animation."""
    return _adapt(VM.read(OR.faithful_path(name)))


# --------------------------------------------------------------------------- compositing


def render_map(
    surf: Sequence[Sequence[str]], objs: Sequence[PlacedObject], title: str = ""
) -> Image.Image:
    H, W = len(surf), len(surf[0])
    canvas = Image.new("RGB", (W * TILE, H * TILE), (0, 0, 0))

    # 1) terrain tiles
    for y in range(H):
        for x in range(W):
            tile_img = terr_tile_img(surf[y][x])
            canvas.paste(tile_img.convert("RGB"), (x * TILE, y * TILE))

    # 2) objects: painter's order = sort by y asc, then by x asc (back-to-front)
    sorted_objs = sorted(objs, key=lambda o: (o.level != 0, o.y, o.x))
    miss = 0
    for o in sorted_objs:
        if o.level != 0:
            continue
        anim = o.animation
        if not anim:
            continue
        groups = get_def(anim)
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


class _Args(argparse.Namespace):
    vmap: str = ""
    compare: str | None = None
    out: str | None = None


def main() -> None:
    ap = argparse.ArgumentParser()
    _ = ap.add_argument("vmap", help=".vmap path to render")
    _ = ap.add_argument("--compare", default=None, help="corpus map name to render alongside")
    _ = ap.add_argument("--out", default=None, help="output PNG path (default auto)")
    args = ap.parse_args(namespace=_Args())

    surf, objs = read_vmap(args.vmap)
    gen_img = render_map(surf, objs, title=os.path.basename(args.vmap))

    if args.compare:
        rsurf, robjs = read_real(args.compare)
        real_img = render_map(rsurf, robjs, title=f"REAL: {args.compare}")
        gap = 8
        canvas = Image.new(
            "RGB",
            (real_img.width + gen_img.width + gap, max(real_img.height, gen_img.height)),
            (0, 0, 0),
        )
        canvas.paste(real_img, (0, 0))
        canvas.paste(gen_img, (real_img.width + gap, 0))
        out_img = canvas
    else:
        out_img = gen_img

    out_path = args.out or os.path.join(
        ROOT, "out", "render", os.path.basename(args.vmap).replace(".vmap", "_editor.png")
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    out_img.save(out_path)
    print(f"wrote {out_path}  ({out_img.width}x{out_img.height})")


if __name__ == "__main__":
    main()

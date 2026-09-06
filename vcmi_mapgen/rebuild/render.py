"""Rendering for the identity-rebuild engine: the zone-tint segmentation PNG and the
realistic editor-sprite side-by-side (original vs rebuilt)."""
import os

from vcmi_mapgen.kit import terrain_segment as TS
from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.kit.render_palette import TERRAIN_RGB as _TERRAIN_RGB
from vcmi_mapgen.rebuild.engine import _bucket_objects, label_zone

ZONE_TINT = [(200, 80, 80), (80, 160, 200), (90, 200, 120), (210, 180, 70),
             (180, 110, 200), (220, 140, 80), (120, 200, 200), (200, 120, 160),
             (150, 170, 90), (110, 130, 220)]

TILE = 9  # px per tile for the schematic segmentation render


def render_segmentation(name: str, out_path: str):
    from PIL import Image, ImageDraw
    fm = OR.load_faithful(name)
    W, H = fm["width"], fm["height"]
    imgs, tables = [], []
    for L, lvl in enumerate(fm["terrain"]):
        zones, zone_label = TS.segment(lvl)
        zone_objs, _ = _bucket_objects(fm["objects"], L, zone_label, zones, W, H)
        img = Image.new("RGB", (W * TILE, H * TILE), (10, 10, 10))
        px = img.load()
        for y in range(H):
            for x in range(W):
                base = _TERRAIN_RGB.get(lvl[y][x]["t"], (0, 0, 0))
                z = zone_label[y][x]
                col = (tuple((b + t) // 2 for b, t in zip(base, ZONE_TINT[z % len(ZONE_TINT)]))
                       if z >= 0 else base)
                for dy in range(TILE):
                    for dx in range(TILE):
                        px[x * TILE + dx, y * TILE + dy] = col
        d = ImageDraw.Draw(img)
        table = []
        for zid in sorted(zones):
            z = zones[zid]
            lab = label_zone(z, zone_objs[zid], W, H)
            table.append((zid, lab, z["area"], len(zone_objs[zid])))
            tx, ty = int(z["centroid"][0] * TILE), int(z["centroid"][1] * TILE)
            d.text((tx - 4, ty - 9), str(zid), fill=(255, 255, 255))
            d.text((tx - 18, ty + 1), lab, fill=(255, 255, 0))
        imgs.append(img)
        tables.append((L, table))
    gap = 12
    canvas = Image.new("RGB", (sum(i.width for i in imgs) + gap * (len(imgs) - 1),
                               max(i.height for i in imgs)), (20, 20, 20))
    x = 0
    for i in imgs:
        canvas.paste(i, (x, 0))
        x += i.width + gap
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    canvas.save(out_path)
    return out_path, tables


def _paint_sort(objs):
    """Canonical paint order so overlapping sprites stack identically across renders.
    renderers.sprites.render_map re-sorts stably by (l!=0, y, x), so this only fixes ties."""
    return sorted(objs, key=lambda o: (o["y"], o["x"], o.get("type", ""),
                                       o.get("subtype", ""),
                                       o.get("template", {}).get("animation", "")))


def editor_render(vmap_path: str, out_path: str, compare_vmap: str | None = None,
                  labels=("SOURCE (faithful)", "REBUILT")):
    """Realistic editor-sprite render. With compare_vmap, render both via the SAME
    read_vmap path (surface, object-identical => visually identical)."""
    from vcmi_mapgen.renderers import sprites as RE
    from PIL import Image
    surf, objs = RE.read_vmap(vmap_path)
    gen = RE.render_map(surf, _paint_sort(objs), title=labels[1])
    if compare_vmap:
        ssurf, sobjs = RE.read_vmap(compare_vmap)
        ref = RE.render_map(ssurf, _paint_sort(sobjs), title=labels[0])
        gap = 8
        out = Image.new("RGB", (ref.width + gen.width + gap,
                                max(ref.height, gen.height)), (0, 0, 0))
        out.paste(ref, (0, 0))
        out.paste(gen, (ref.width + gap, 0))
    else:
        out = gen
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    out.save(out_path)
    return out_path

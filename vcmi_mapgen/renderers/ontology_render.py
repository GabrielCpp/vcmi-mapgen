"""Render every leaf of the ontology tree to its full path on disk:
out/ontology/<CLUSTER>/<PURPOSE>/<type>/<terrain>/<leaf>.png

Documentation/debug tooling: it renders the object taxonomy itself (`ontology.build_tree()`),
never a generated or rebuilt map, so it stays outside the step/pipeline model entirely — `cli.py`
calls :func:`render_ontology` directly.
"""
import collections
import csv
import os
import shutil

from vcmi_mapgen import ontology as ON
from vcmi_mapgen.kit.paths import project_root
from vcmi_mapgen.renderers import sprites as RE

ROOT = project_root()

# Editor-style passability overlay colours (the four real mask states; see ontology mask docs).
_MASK_OVERLAY_COLORS = {
    "B": (235, 40, 40, 120),    # blocked
    "X": (245, 140, 25, 150),   # blocked + visitable (a building's action tile, visited adjacent)
    "A": (245, 225, 40, 165),   # passable + visitable (walk-onto pickup / stand-on tile)
    "V": (70, 170, 255, 85),    # passable overlay / overhang
}


def _mask_overlay(full_sprite, grid, tile):
    """Editor-style passability overlay: the object's full 6x8 B/X/A/V `grid` drawn TRANSLUCENT
    over the FULL (uncropped) sprite canvas. H3 sprites are CENTRED on their footprint and sit on
    the ground, so the mask's active bounding box is centred HORIZONTALLY and bottom-aligned
    VERTICALLY within the sprite's tile grid. (The objects.txt grid is NOT simply left-justified:
    e.g. a 1-tile pine whose art is on the right tile, a seer-hut tile centred under a 3-wide hut,
    a town gate at the centre column -- absolute `sx = c` lands those on the wrong, often empty,
    tile.) Validated against art: pine `B` on the trunk, wood pile `A` on the logs, seer hut
    centred, town gate at the sprite centre. '.' grid cells are outside the footprint and not drawn.
    Cropped to the union of sprite content + footprint. (This sprite-canvas frame is distinct from
    the map-placement bottom-RIGHT anchor in renderers.sprites/kit.objects -- do not conflate them.)"""
    from PIL import Image, ImageDraw

    base = full_sprite.convert("RGBA")
    cols_t, rows_t = base.width // tile, base.height // tile
    act = [(r, c) for r, row in enumerate(grid) for c, ch in enumerate(row) if ch != "."]
    if not act:
        return base
    r0 = min(r for r, _ in act); r1 = max(r for r, _ in act)
    c0 = min(c for _, c in act); c1 = max(c for _, c in act)
    cw, chh = c1 - c0 + 1, r1 - r0 + 1
    coff = (cols_t - cw + 1) // 2              # centre footprint horizontally (round outward)
    roff = rows_t - chh                        # bottom-align vertically (object sits on the ground)

    ov = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    cells = []                                 # tile-pixel boxes covered by a non-'.' grid cell
    for r in range(r0, r1 + 1):
        for c in range(c0, c1 + 1):
            ch = grid[r][c]
            col = _MASK_OVERLAY_COLORS.get(ch)
            if col is None:                    # '.' (passable inside bbox is 'V'; truly outside skipped)
                continue
            sx, sy = (c - c0) + coff, (r - r0) + roff   # centred column; rows bottom-aligned
            if not (0 <= sx < cols_t and 0 <= sy < rows_t):
                continue
            x0, y0 = sx * tile, sy * tile
            d.rectangle((x0, y0, x0 + tile - 1, y0 + tile - 1), fill=col,
                        outline=(0, 0, 0, 90))
            if ch != "V":
                cells.append((x0, y0, x0 + tile, y0 + tile))
    base.alpha_composite(ov)

    sb = base.getbbox()                        # union of sprite content + footprint
    boxes = [b for b in [sb] if b] + cells
    if boxes:
        x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
        x1 = max(b[2] for b in boxes); y1 = max(b[3] for b in boxes)
        base = base.crop((x0, y0, x1, y1))
    return base


def render_ontology(out: str | None = None) -> None:
    """Render every leaf of the ontology tree to its full path on disk:
    out/ontology/<CLUSTER>/<PURPOSE>/<type>/<terrain>/<leaf>.png
    and, next to each, `<leaf>.mask.png` -- the same sprite with its passability mask overlaid
    the way the editor draws it (translucent B/X/A/V cells, bottom-left/footprint justified).

    The directory layout mirrors the hardcoded ontology.TAXONOMY exactly -- the absolute object list
    the VCMI/H3 map editor can place (from objects.txt), every CLUSTER -> PURPOSE -> type -> terrain
    -> leaf edge down to the sprite. A leaf's sprite is its `animation` DEF (frame 0); colour-keyed
    quest objects (border gate/guard, keymaster tent) sit under "land" with one leaf per colour.
    """
    out_root = out or os.path.join(ROOT, "out", "ontology")
    tree = ON.build_tree()

    if os.path.isdir(out_root):                 # rebuild cleanly (path shape may change across runs)
        shutil.rmtree(out_root)
    os.makedirs(out_root, exist_ok=True)

    rows = []
    per_cluster = collections.Counter()
    skipped = 0
    for cluster, purpose, typ, terrain, name, anim in ON.iter_leaves(tree):
        groups = RE.get_def(anim)
        if not groups or not groups[0]:
            skipped += 1
            continue
        full = groups[0][0]                     # full canvas (kept for tile-aligned mask overlay)
        bbox = full.getbbox()                   # trim transparent margin for the plain sprite
        sprite = full.crop(bbox) if bbox else full
        # collapse redundant consecutive levels (DECORATION/DECORATION/..., VISIBLE/TOWN/TOWN/...).
        chain = [cluster, purpose, typ]
        parts = [chain[0]] + [x for i, x in enumerate(chain[1:], 1) if x != chain[i - 1]]
        parts.append(terrain)
        # colour/subtype-keyed leaves (name != animation) become a faction/colour FOLDER level, so
        # towns read as VISIBLE/TOWN/<faction>/... rather than one cryptic file per faction.
        if name != anim:
            parts.append(name)
        leaf = anim
        d = os.path.join(out_root, *parts)
        os.makedirs(d, exist_ok=True)
        png = os.path.join(d, f"{leaf}.png")
        sprite.save(png)
        mpng = os.path.join(d, f"{leaf}.mask.png")   # same sprite with the passability mask overlaid
        gridmask = ON.full_mask_of(anim) or ON.mask_of(anim)
        _mask_overlay(full, gridmask, RE.TILE).save(mpng)
        per_cluster[cluster] += 1
        rows.append((cluster, purpose, typ, terrain, name, anim,
                     os.path.relpath(png, out_root), os.path.relpath(mpng, out_root)))

    with open(os.path.join(out_root, "index.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(("cluster", "purpose", "type", "terrain", "leaf", "animation", "png", "mask_png"))
        w.writerows(sorted(rows))

    print(f"ontology catalog -> {out_root}/  ({len(rows)} PNGs, {skipped} skipped: no sprite)")
    for c in ON.CLUSTERS:
        print(f"  {c:11s} {per_cluster[c]:5d}")
    print(f"  index.csv ({len(rows)} rows)")

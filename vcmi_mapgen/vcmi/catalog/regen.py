"""Rebuild the catalog's two JSON tables from the editor's own object table.

The taxonomy is derived from the AUTHORITATIVE VCMI/H3 object table (objects.txt in the LOD),
the absolute list the map editor places, and written to ``data/catalog/taxonomy.json`` and
``data/catalog/leaf_meta.json``. Run ``uv run python -m vcmi_mapgen.cli regen-ontology``.
objects.txt columns: DEF, passability(48), triggers(48), allowedTerrains(9), nativeTerrain(9),
class, subclass, group, isOverlay. The 9-bit terrain masks are MSB->LSB = terrain 8..0
(water..dirt); bit i means terrain (8 - i).
"""

import json
import struct
from collections.abc import Mapping
from functools import cache

from vcmi_mapgen.vcmi.catalog.objects import resolve
from vcmi_mapgen.vcmi.catalog.tables import (
    COLOR_KEYED_NAMES,
    GATE_COLORS,
    LEAF_TERRAINS,
    SUBTYPE_KEYED_NAMES,
    LeafMeta,
    Taxonomy,
    table_path,
)
from vcmi_mapgen.vcmi.config import VcmiConfig
from vcmi_mapgen.vcmi.footprint import Mask
from vcmi_mapgen.vcmi.formats.lod import LodIndex
from vcmi_mapgen.vcmi.terrain import name_of


def _decode_mask(passability: str, triggers: str) -> Mask:
    """Decode the objects.txt passability(48)+triggers(48) bitfields into the B/A/V footprint
    mask rows (`vcmi.footprint.footprint_of` semantics: B=blocking, A=visitable anchor, V=visible
    overlay). This reproduces `vcmi.formats.vmap.mask.build_mask_from_h3m` (the corpus mask source)
    bit-for-bit: the
    6x8 grid defaults to 'V', a cell is 'A' if its trigger bit is set else 'B' if its
    passability bit is clear (H3: clear=blocked); rows/cols that are all-'V' are trimmed. The
    grid is anchored bottom-right and stored rotated 180° (rows bottom-to-top AND columns
    right-to-left), so BOTH are reversed to sprite-align it — reversing rows only leaves every
    asymmetric footprint horizontally mirrored vs the art (the v5.2 sawmill-entrance bug; see
    :func:`_decode_mask_grid`). Kept bit-for-bit in sync with
    `vcmi.formats.vmap.mask.build_mask_from_h3m` (the corpus mask source)."""

    def rows(bits: str) -> list[str]:
        return [bits[r * 8 : (r + 1) * 8] for r in range(6)]

    P, T = rows(passability), rows(triggers)
    grid = [["V"] * 8 for _ in range(6)]
    for r in range(6):
        for c in range(8):
            blocked = P[r][c] == "0"  # H3: passability bit clear == blocked
            visit = T[r][c] == "1"
            # four states from two independent bits; 'X' = blocked AND visitable (building action
            # tile, visited from an adjacent tile) — keep its blocked-ness instead of collapsing to
            # A
            grid[r][c] = ("X" if blocked else "A") if visit else ("B" if blocked else "V")
    # only an object with a solid BODY ('B' cells) keeps a blocked visit tile ('X', visited from
    # adjacent); a bodyless single visit tile is a walk-onto pickup -> 'A' (passable). See
    # build_mask.
    if not any(grid[r][c] == "B" for r in range(6) for c in range(8)):
        for r in range(6):
            for c in range(8):
                if grid[r][c] == "X":
                    grid[r][c] = "A"
    grid = [row[::-1] for row in grid[::-1]]  # 180°: rows bottom-to-top, cols right-to-left
    keep_r = [r for r in range(6) if any(ch != "V" for ch in grid[r])]
    keep_c = [c for c in range(8) if any(grid[r][c] != "V" for r in range(6))]
    if not keep_r or not keep_c:
        return ("B",)
    return tuple("".join(grid[r][c] for c in keep_c) for r in keep_r)


def _decode_mask_grid(passability: str, triggers: str) -> Mask:
    """Return the FULL 6x8 visual footprint grid (rows top->bottom, cols left->right) aligned to
    the SPRITE, WITHOUT trimming -- what an editor-style overlay needs. H3 object masks are anchored
    at the BOTTOM-RIGHT and read bottom-to-top, RIGHT-to-LEFT, so the storage grid is rotated 180°
    (rows reversed AND columns reversed) to put it sprite-aligned. (Reversing rows only -- as the
    placement decoder :func:`_decode_mask` does -- leaves asymmetric footprints horizontally
    MIRRORED vs the art: e.g. a pine clump's blocked trunks, or a sawmill's visit tile, land on the
    wrong side.) '.' marks a tile outside the footprint (not drawn); a passable tile INSIDE the
    active bounding box is 'V' (overhang)."""
    grid = _storage_mask_grid(passability, triggers)
    if not any(grid[r][c] == "B" for r in range(6) for c in range(8)):
        _demote_entrances(grid)
    grid = [row[::-1] for row in grid[::-1]]  # 180°: rows bottom-to-top, cols right-to-left
    _fill_overhang(grid)
    return tuple("".join(row) for row in grid)


def _storage_mask_grid(passability: str, triggers: str) -> list[list[str]]:
    def rows(bits: str) -> list[str]:
        return [bits[r * 8 : (r + 1) * 8] for r in range(6)]

    P, T = rows(passability), rows(triggers)
    grid = [["."] * 8 for _ in range(6)]
    for r in range(6):
        for c in range(8):
            blocked = P[r][c] == "0"
            visit = T[r][c] == "1"
            grid[r][c] = ("X" if blocked else "A") if visit else ("B" if blocked else ".")
    return grid


def _demote_entrances(grid: list[list[str]]) -> None:
    for r in range(6):
        for c in range(8):
            if grid[r][c] == "X":
                grid[r][c] = "A"


def _fill_overhang(grid: list[list[str]]) -> None:
    act = [(r, c) for r in range(6) for c in range(8) if grid[r][c] != "."]
    if act:  # passable tiles inside the footprint bbox -> 'V'
        r0, r1 = min(r for r, _ in act), max(r for r, _ in act)
        c0, c1 = min(c for _, c in act), max(c for _, c in act)
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                if grid[r][c] == ".":
                    grid[r][c] = "V"


@cache
def _full_grids(index: LodIndex) -> dict[str, Mask]:
    grids: dict[str, Mask] = {}
    for anim, p1, p2 in _objects_txt_raw(index):
        if len(p1) == 48 and len(p2) == 48:
            grids[anim] = _decode_mask_grid(p1, p2)
    return grids


def full_mask_of(index: LodIndex, animation: str) -> Mask | None:
    """The full 6-row x 8-col visual footprint grid (B/X/A/V/'.') for an animation, bottom-left
    anchored -- for editor-style overlays. Empty ('.') outside the object footprint. See
    :func:`_decode_mask_grid`."""
    return _full_grids(index).get((animation or "").lower())


def _def_tile_dims(index: LodIndex, animation: str) -> tuple[int, int] | None:
    """(width, height) of an animation's sprite in 32px TILES, from the DEF file header in the
    H3 LOD (type u32, width u32, height u32). None when the DEF is absent."""
    data = index.read(animation + ".def")
    if not data or len(data) < 12:
        return None
    _typ, w, h = struct.unpack_from("<III", data, 0)
    if not (0 < w <= 8 * 32 and 0 < h <= 6 * 32):
        return None
    return ((w + 31) // 32, (h + 31) // 32)


def _decode_mask_full(passability: str, triggers: str, tile_dims: tuple[int, int] | None) -> Mask:
    """The bottom-right window of the full sprite-aligned footprint grid
    (:func:`_decode_mask_grid`), sized to the sprite's tile extent — 'X' entrances kept
    distinct from plain visitable 'A' (see :func:`vmap_mask_of`, which translates X->A). VCMI
    draws an object only on mask-covered tiles, so a mask trimmed to the blocked bbox
    (:func:`_decode_mask`) truncates tall sprites in-game and is too small for gameplay
    placement too: it lets other objects (or a guard's own approach search) land on tiles that
    are visually part of the sprite (the v5.3 sawmill-guard-hidden-behind-trees bug). Real RMG
    .vmaps V-fill to the sprite extent, so this is the ground truth for :func:`mask_of` as well
    as :func:`vmap_mask_of` — both in the same LEFT-TO-RIGHT column order as this function's
    output and the corpus's `vcmi.formats.vmap.mask.build_mask_from_h3m` masks (col 0 =
    leftmost tile, anchor is the last column: `tx = ax - (ww - 1 - c)`, see
    `vcmi.footprint.footprint_of`'s docstring); no column
    reversal is needed anywhere in this decode chain — the v5.4 sawmill-guard-wrong-side bug
    turned out to be in the CONSUMER (`footprint_of`/`_cells` treating col 0 as the anchor instead
    of the leftmost tile), not in this decode chain."""
    grid = _decode_mask_grid(passability, triggers)  # 6 rows x 8 cols, '.' outside
    act = [(r, c) for r in range(6) for c in range(8) if grid[r][c] != "."]
    if not act:
        return ("B",)
    wt, ht = tile_dims if tile_dims else (0, 0)
    ht = max(1, min(6, ht), 6 - min(r for r, _ in act))  # never cut an active cell
    wt = max(1, min(8, wt), 8 - min(c for _, c in act))
    return tuple(
        "".join("V" if ch == "." else ch for ch in grid[r][8 - wt :]) for r in range(6 - ht, 6)
    )


def _objects_txt_raw(index: LodIndex) -> list[tuple[str, str, str]]:
    """[(animation, passability48, triggers48), ...] straight from objects.txt (no decode)."""
    raw = index.read("objects.txt")
    if raw is None:
        raise RuntimeError("objects.txt not found in the H3 LOD")
    out: list[tuple[str, str, str]] = []
    for line in raw.decode("latin1", "replace").splitlines()[1:]:
        p = line.split()
        if len(p) < 7 or not p[0].lower().endswith(".def"):
            continue
        anim = p[0][:-4].lower()
        if anim == "default":
            continue
        out.append((anim, p[1], p[2]))
    return out


def _objects_txt_records(index: LodIndex) -> list[tuple[str, str, str, int, int, Mask]]:
    """[(animation, allowedMask, nativeMask, class, subclass, mask), ...] from the LOD's
    objects.txt. ``mask`` is the decoded B/A/V footprint (see :func:`_decode_mask`)."""
    raw = index.read("objects.txt")
    if raw is None:
        raise RuntimeError("objects.txt not found in the H3 LOD")
    recs: list[tuple[str, str, str, int, int, Mask]] = []
    for line in raw.decode("latin1", "replace").splitlines()[1:]:
        p = line.split()
        if len(p) < 7 or not p[0].lower().endswith(".def"):
            continue
        anim = p[0][:-4].lower()
        if anim == "default":
            continue
        mask = _decode_mask(p[1], p[2]) if len(p[1]) == 48 and len(p[2]) == 48 else ("B",)
        recs.append((anim, p[3], p[4], int(p[5]), int(p[6]), mask))
    return recs


def _mask_terrains(mask: str) -> set[str]:
    """9-bit objects.txt terrain mask -> set of land/water terrain names (bit i -> terrain 8-i)."""
    return {name_of(8 - i) for i, c in enumerate(mask) if c == "1"}


def _template_terrains(allowed_mask: str, native_mask: str, coupled: bool) -> list[str]:
    """Terrain node(s) for a template: the native terrain(s) for terrain-coupled objects, else a
    coarse land/water bucket (terrain-independent objects carry a placeholder native terrain)."""
    if coupled:
        native = sorted(_mask_terrains(native_mask))
        if not native:
            return ["land"]
        if len([t for t in native if t != "water"]) >= 8:  # native to (essentially) all land
            return ["land"]
        return native
    allowed = _mask_terrains(allowed_mask)
    if "water" in allowed and not any(t != "water" for t in allowed):
        return ["water"]
    return ["land"]


def _derive_leaf_meta(index: LodIndex) -> dict[str, LeafMeta]:
    """{animation: {"cls", "sub", "mask"}} for every objects.txt template — the per-animation
    placement metadata the ontology exposes via :func:`identity_of` / :func:`mask_of`, windowed
    to the sprite's full tile extent and already in `footprint_of`'s anchor convention
    (:func:`_decode_mask_full`), so the same footprint serves gameplay placement AND (with X->A)
    `.vmap` export (:func:`vmap_mask_of`) with no reversal in between."""
    bits = {anim: (p1, p2) for anim, p1, p2 in _objects_txt_raw(index)}
    meta: dict[str, LeafMeta] = {}
    for anim, _allowed, _native, cls, sub, mask in _objects_txt_records(index):
        p1, p2 = bits.get(anim, ("", ""))
        if len(p1) == 48 and len(p2) == 48:
            leaf_mask = _decode_mask_full(p1, p2, _def_tile_dims(index, anim))
        else:
            leaf_mask = mask
        meta[anim] = LeafMeta(cls, sub, leaf_mask)
    return meta


def _derive_taxonomy(index: LodIndex) -> Taxonomy:
    """Build the CLUSTER->PURPOSE->type->terrain->leaf tree from objects.txt + the ontology."""
    raw: dict[str, dict[str, dict[str, dict[str, dict[str, str]]]]] = {}
    for anim, allowed, native, cls, sub, _mask in _objects_txt_records(index):
        r = resolve(cls, sub)
        typ = r.name
        if typ in COLOR_KEYED_NAMES:
            leaf_name = GATE_COLORS.get(sub, str(sub))
        elif typ in SUBTYPE_KEYED_NAMES:
            leaf_name = r.subtype  # faction (castle, rampart, ...)
        else:
            leaf_name = anim
        terrains = LEAF_TERRAINS.get(anim) or _template_terrains(allowed, native, r.terrain_coupled)
        for terrain in terrains:
            node = (
                raw.setdefault(r.cluster, {})
                .setdefault(r.purpose, {})
                .setdefault(typ, {})
                .setdefault(terrain, {})
            )
            node[leaf_name] = anim
    # compact each terrain node: a plain sorted list when leaf names == animations, else a dict.
    tree: Taxonomy = {}
    for cluster, purposes in raw.items():
        for purpose, types in purposes.items():
            for typ, terrains in types.items():
                for terr, leaves in terrains.items():
                    compact: list[str] | dict[str, str] = (
                        sorted(leaves.values())
                        if all(k == v for k, v in leaves.items())
                        else leaves
                    )
                    tree.setdefault(cluster, {}).setdefault(purpose, {}).setdefault(typ, {})[
                        terr
                    ] = compact
    return tree


type _FmtNode = str | list[str] | Mapping[str, _FmtNode]


def _fmt(obj: _FmtNode, ind: int = 0) -> str:
    """Pretty-print the taxonomy as JSON (nested dicts indented and key-sorted; leaves inline)."""
    sp = "    " * ind
    if isinstance(obj, str):
        return json.dumps(obj)
    if isinstance(obj, list):
        return "[" + ", ".join(json.dumps(x) for x in obj) + "]"
    if obj and all(isinstance(v, str) for v in obj.values()):
        return "{" + ", ".join(f"{json.dumps(k)}: {json.dumps(v)}" for k, v in obj.items()) + "}"
    items = [f"{sp}    {json.dumps(k)}: {_fmt(obj[k], ind + 1)}" for k in sorted(obj)]
    return "{\n" + ",\n".join(items) + f"\n{sp}}}"


def _fmt_leaf_meta(meta: dict[str, LeafMeta]) -> str:
    """One compact JSON line per animation: `"anim": [cls, sub, ["row", ...]]`."""
    lines = [
        f"    {json.dumps(anim)}: {json.dumps([m.cls, m.sub, list(m.mask)])}"
        for anim, m in sorted(meta.items())
    ]
    return "{\n" + ",\n".join(lines) + "\n}\n"


def write_tables(tree: Taxonomy, meta: dict[str, LeafMeta]) -> None:
    """Write the taxonomy and the per-animation placement metadata as the catalog's JSON."""
    table_path("taxonomy.json").parent.mkdir(parents=True, exist_ok=True)
    _ = table_path("taxonomy.json").write_text(_fmt(tree) + "\n")
    _ = table_path("leaf_meta.json").write_text(_fmt_leaf_meta(meta))


def write_type_classes(config: VcmiConfig) -> None:
    """Write VCMI's object type to class id table, which answers a type's purpose."""
    types = {name: cid for cid, (name, _subs) in config.classes.items()}
    _ = table_path("vcmi_types.json").write_text(
        json.dumps(dict(sorted(types.items())), indent=1) + "\n"
    )


def regenerate(index: LodIndex, config: VcmiConfig) -> Taxonomy:
    """Derive the taxonomy + per-animation placement metadata from objects.txt and the type
    table from VCMI's config, and rewrite the three JSON tables."""
    tree = _derive_taxonomy(index)
    write_tables(tree, _derive_leaf_meta(index))
    write_type_classes(config)
    return tree

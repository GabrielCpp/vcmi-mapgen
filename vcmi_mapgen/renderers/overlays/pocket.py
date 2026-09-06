"""PocketOverlay — magenta gradient over guard-sealed pocket regions."""
from __future__ import annotations

import collections
import colorsys

from PIL import Image, ImageDraw

from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.pipeline import MapState
from vcmi_mapgen.renderers.overlays import _tiles
from vcmi_mapgen.renderers.overlays._tiles import NB8
from vcmi_mapgen.renderers.overlays.base import MapOverlay, TILE

_MAX_SEALED = 14  # BFS cap per component; pocket grammar max size


class PocketOverlay(MapOverlay):
    """Highlight, in a magenta depth gradient, every passable tile a hero cannot
    reach without fighting a placed guard.

    For each placed guard's 3x3 zone of control (ZoC), finds the bounded
    8-connected passable region behind it (capped at 14 tiles -- larger means the
    guard doesn't actually seal anything). Regions sealed by more than one guard
    are merged. Darker magenta = near the ZoC entrance, lighter = deepest tile.

    Visit tiles of ordinary structures (state.zones aside) are always excluded
    from the passable space this searches, since they're "owned" by the
    structure rather than open pocket floor.

    Args:
        exclude_loot_zones: also exclude tiles belonging to a loot zone (reached
            via a gate/monolith access pair) -- a distinct access mechanic that
            should never show a magenta seal. Needs `state.zones[level]`.
    """

    def __init__(self, exclude_loot_zones: bool = False) -> None:
        self._exclude_loot_zones = exclude_loot_zones

    def apply(self, state: MapState, level: int) -> Image.Image:
        surf = state.surfs.get(level) or state.cells.get(level)
        if not surf:
            return self._blank(*self._grid_size(state, level))
        W, H = len(surf[0]), len(surf)
        objs = state.objs

        passable = _tiles.passable_tiles(surf, objs, level)
        _bg, _sb, struct_visit, _solo = _tiles.classify_objects(objs, level)
        passable -= struct_visit
        if self._exclude_loot_zones:
            zones = state.zones.get(level)
            if zones:
                passable -= _tiles.loot_zone_tiles(zones, objs, level)

        img = Image.new("RGBA", (W * TILE, H * TILE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        for zoc, sealed in _sealed_regions(objs, level, passable, W, H):
            dist = _bfs_distances(sealed, zoc)
            max_d = max(dist.values()) if dist else 0
            for (x, y), d in dist.items():
                t = d / max_d if max_d else 0.0
                draw.rectangle(
                    [x * TILE, y * TILE, (x + 1) * TILE - 1, (y + 1) * TILE - 1],
                    fill=_magenta_color(t),
                )
        return img


# ---------------------------------------------------------------------------
# guard-centric sealed-region detection
# ---------------------------------------------------------------------------

def _sealed_regions(objs, level, passable, W, H):
    """(zoc, sealed_tiles) pairs, one per guard, with overlapping regions merged
    (the same nook guarded by more than one guard)."""
    regions = []
    for o in objs:
        if o.get("l", 0) != level or o.get("purpose") != "GUARD":
            continue
        mask = o.get("mask") or (o.get("template") or {}).get("mask")
        if not mask:
            continue
        for ax, ay in OR.mask_interactive_cells(mask, o.get("x", 0), o.get("y", 0)):
            zoc = frozenset(
                (ax + dx, ay + dy)
                for dx in range(-1, 2) for dy in range(-1, 2)
                if 0 <= ax + dx < W and 0 <= ay + dy < H
            )
            passable_no_zoc = passable - zoc
            sealed, seen = set(), set()
            for tx, ty in sorted(zoc):
                for dx, dy in NB8:
                    nb = (tx + dx, ty + dy)
                    if nb in zoc or nb in seen or nb not in passable_no_zoc:
                        continue
                    comp, q, leaked = {nb}, collections.deque([nb]), False
                    while q and not leaked:
                        cx, cy = q.popleft()
                        for ddx, ddy in NB8:
                            n2 = (cx + ddx, cy + ddy)
                            if n2 in zoc or n2 in comp or n2 not in passable_no_zoc:
                                continue
                            comp.add(n2)
                            if len(comp) > _MAX_SEALED:
                                leaked = True
                                break
                            q.append(n2)
                    if not leaked:
                        seen |= comp
                        sealed |= comp
            if sealed:
                regions.append([set(zoc), sealed])

    merged = []
    used = [False] * len(regions)
    for i in range(len(regions)):
        if used[i]:
            continue
        m_zoc, m_sealed = set(regions[i][0]), set(regions[i][1])
        used[i] = True
        changed = True
        while changed:
            changed = False
            for j in range(len(regions)):
                if used[j]:
                    continue
                if regions[j][1] & m_sealed:
                    m_zoc |= regions[j][0]
                    m_sealed |= regions[j][1]
                    used[j] = True
                    changed = True
        merged.append((frozenset(m_zoc), m_sealed))
    return merged


def _bfs_distances(pocket: frozenset, entrance: frozenset) -> dict:
    """BFS distance from entrance into pocket body (8-connected)."""
    dist: dict = {}
    q = collections.deque()
    for gx, gy in entrance:
        for dx, dy in NB8:
            nb = (gx + dx, gy + dy)
            if nb in pocket and nb not in dist:
                dist[nb] = 0
                q.append(nb)
    while q:
        t = q.popleft()
        tx, ty = t
        for dx, dy in NB8:
            nb = (tx + dx, ty + dy)
            if nb in pocket and nb not in dist:
                dist[nb] = dist[t] + 1
                q.append(nb)
    return dist


def _magenta_color(t: float) -> tuple:
    """t=0 (entrance, darkest) -> t=1 (deepest, lightest). Returns RGBA."""
    v = 0.30 + 0.70 * t
    r, g, b = colorsys.hsv_to_rgb(300 / 360, 0.90, v)
    return (int(r * 255), int(g * 255), int(b * 255), 130)

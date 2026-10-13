"""Zone-border geometry: which zone owns each land tile and which open pairs cross a zone
border, or sit closer than the wall between their zones allows. The vegetation border plan
reads them."""

from collections.abc import Collection, Container, Mapping, Sequence
from typing import cast

import numpy as np

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Tile, Zone


def zone_owner(
    catalog: Catalog, zones: Mapping[int, Zone]
) -> tuple[dict[Tile, int], dict[Tile, str]]:
    """Land tile to zone id and terrain name, water and rock zones left out."""
    owner: dict[Tile, int] = {}
    tname: dict[Tile, str] = {}
    for zid, z in sorted(zones.items()):
        if z.terrain_type.is_barrier:
            continue
        terr = catalog.terrain_name(z.terrain_type)
        for t in z.tiles_set:
            owner[t] = zid
            tname[t] = terr
    return owner, tname


def cross_pairs(
    open_all: Collection[Tile],
    owner: Mapping[Tile, int],
    bands: Container[tuple[Tile, int]],
    skip_tiles: Container[Tile] = (),
) -> tuple[list[tuple[Tile, Tile]], list[tuple[Tile, Tile]]]:
    """8-adjacent open pairs across a zone border, each unordered pair once. ``bands`` holds
    each entrance band tile with the zone its entrance leads to.

    Returns (plain pairs, pairs whose tile on either side is a band toward the other)."""
    pairs: list[tuple[Tile, Tile]] = []
    band_pairs: list[tuple[Tile, Tile]] = []
    for t in sorted(open_all):
        a = owner.get(t)
        if a is None or t in skip_tiles:
            continue
        for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
            n = (t[0] + dx, t[1] + dy)
            if n not in open_all or n in skip_tiles:
                continue
            b = owner.get(n)
            if b is not None and b != a:
                if (t, b) in bands or (n, a) in bands:
                    band_pairs.append((t, n))
                else:
                    pairs.append((t, n))
    return pairs, band_pairs


def closing_pairs(
    pairs: Sequence[tuple[Tile, Tile]],
    owner: Mapping[Tile, int],
    open_pairs: Container[tuple[int, int]],
) -> list[tuple[Tile, Tile]]:
    """The crossings of ``pairs`` whose zone pair ``(a, b)``, ``a < b``, is not in
    ``open_pairs``: an open border stays walkable along its whole front."""
    out: list[tuple[Tile, Tile]] = []
    for t, n in pairs:
        a, b = owner[t], owner[n]
        if (min(a, b), max(a, b)) not in open_pairs:
            out.append((t, n))
    return out


def deep_pairs(
    open_all: Collection[Tile], owner: Mapping[Tile, int], depths: Mapping[tuple[int, int], int]
) -> list[tuple[Tile, Tile]]:
    """The open pairs of two zones ``(a, b)``, ``a < b``, more than one tile apart and no
    farther apart in Chebyshev distance than the wall width ``depths`` gives them, each
    unordered pair once, in tile order."""
    reach = max(depths.values(), default=1)
    tiles = [t for t in open_all if t in owner]
    if reach < 2 or not tiles:
        return []
    ids = sorted({owner[t] for t in tiles})
    index = {z: i for i, z in enumerate(ids)}
    wide = np.zeros((len(ids) + 1, len(ids) + 1), dtype=np.int32)
    for (a, b), d in depths.items():
        if a in index and b in index:
            wide[index[a], index[b]] = wide[index[b], index[a]] = d
    w = max(x for x, _ in tiles) + 1
    h = max(y for _, y in tiles) + 1
    grid = np.full((h + 2 * reach, w + 2 * reach), len(ids), dtype=np.int32)
    for x, y in tiles:
        grid[y + reach, x + reach] = index[owner[(x, y)]]
    here = grid[reach : reach + h, reach : reach + w]
    out: list[tuple[Tile, Tile]] = []
    for dy in range(reach + 1):
        for dx in range(-reach, reach + 1):
            far = max(abs(dx), dy)
            if far < 2 or (dy == 0 and dx < 0):
                continue
            there = grid[reach + dy : reach + dy + h, reach + dx : reach + dx + w]
            yx = cast(list[list[int]], np.argwhere(wide[here, there] >= far).tolist())
            out += [((x, y), (x + dx, y + dy)) for y, x in yx]
    return sorted(out)

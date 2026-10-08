"""Zone-border geometry: which zone owns each land tile and which open pairs cross a zone
border. The vegetation border plan reads them."""

from collections.abc import Collection, Container, Mapping, Sequence

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

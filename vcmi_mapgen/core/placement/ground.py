"""The ground rule (map-math 4.1, C5): every solid cell of an object stands on a tile whose
terrain the object's identity allows, by the catalog's terrain coupling. A solid cell blocks
or is visited. Overlay cells and cells past the map edge stand on nothing."""

from collections.abc import Sequence
from functools import cache

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Footprint, Identity, Tile
from vcmi_mapgen.core.model.terrain import Terrain

type Ground = Sequence[Sequence[int]]


def allowed_terrains(catalog: Catalog, kind: str) -> frozenset[Terrain]:
    """Every terrain the catalog lets `kind` stand on."""
    return frozenset(t for t in Terrain if catalog.allowed_on(kind, t))


def solid_tiles(footprint: Footprint, anchor: Tile) -> list[Tile]:
    """The cells of `footprint` anchored at `anchor` that block or are visited."""
    x, y = anchor
    return [(x + dx, y + dy) for dx, dy in _solid(footprint)]


@cache
def _solid(footprint: Footprint) -> tuple[Tile, ...]:
    return tuple(t for t, role in footprint.at(0, 0) if role.blocks or role.interactive)


def on_ground(catalog: Catalog, kind: str, tiles: Sequence[Tile], ground: Ground) -> bool:
    """Whether every on-map tile of `tiles` has a terrain `kind` may stand on. An empty
    `ground` checks nothing."""
    if not ground:
        return True
    h, w = len(ground), len(ground[0])
    return all(
        catalog.allowed_on(kind, ground[ty][tx]) for tx, ty in tiles if 0 <= tx < w and 0 <= ty < h
    )


def stands(catalog: Catalog, ident: Identity, anchor: Tile, ground: Ground) -> bool:
    """Whether `ident` anchored at `anchor` keeps every solid cell on allowed ground."""
    return on_ground(catalog, ident.kind, solid_tiles(ident.footprint, anchor), ground)

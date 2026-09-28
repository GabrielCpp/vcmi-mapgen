"""4-connected components of a tile set, and the open ground walled off from every walkable
anchor."""

from __future__ import annotations

from collections.abc import Collection
from collections.abc import Set as AbstractSet

from vcmi_mapgen.core.grid.reach import distances, reach
from vcmi_mapgen.core.model import Tile


def open_islands(
    land: AbstractSet[Tile], blocking: AbstractSet[Tile], anchors: Collection[Tile]
) -> list[set[Tile]]:
    """4-connected open components of `land - blocking` that contain no anchor tile or
    tile next to one."""
    anchor_zone: set[Tile] = set()
    for x, y in anchors:
        anchor_zone.update(((x, y), (x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    open_tiles = land - blocking
    seen: set[Tile] = set()
    islands: list[set[Tile]] = []
    for start in sorted(open_tiles):
        if start in seen:
            continue
        comp = reach(open_tiles, [start])
        seen |= comp
        if not comp & anchor_zone:
            islands.append(comp)
    return islands


def components(tiles: AbstractSet[Tile]) -> dict[Tile, int]:
    """Label each tile with its 4-connected component inside ``tiles``."""
    label: dict[Tile, int] = {}
    n = 0
    for s in sorted(tiles):
        if s in label:
            continue
        for t in distances(tiles, [s]):
            label[t] = n
        n += 1
    return label

"""Connected components of a tile set, 4-connected unless told otherwise, and the open ground
walled off from every walkable anchor."""

from __future__ import annotations

from collections.abc import Collection
from collections.abc import Set as AbstractSet

from vcmi_mapgen.core.grid.reach import STEPS4, Steps, distances, reach
from vcmi_mapgen.core.model import Tile


def open_islands(
    land: AbstractSet[Tile],
    blocking: AbstractSet[Tile],
    anchors: Collection[Tile],
    steps: Steps = STEPS4,
) -> list[set[Tile]]:
    """The open components of `land - blocking`, joined by `steps`, that contain no anchor
    tile or tile one step from one."""
    anchor_zone: set[Tile] = set()
    for x, y in anchors:
        anchor_zone.add((x, y))
        anchor_zone.update((x + dx, y + dy) for dx, dy in steps)
    open_tiles = land - blocking
    seen: set[Tile] = set()
    islands: list[set[Tile]] = []
    for start in sorted(open_tiles):
        if start in seen:
            continue
        comp = reach(open_tiles, [start], steps)
        seen |= comp
        if not comp & anchor_zone:
            islands.append(comp)
    return islands


def components(tiles: AbstractSet[Tile], steps: Steps = STEPS4) -> dict[Tile, int]:
    """Label each tile with its component inside ``tiles``, joined by ``steps``."""
    label: dict[Tile, int] = {}
    n = 0
    for s in sorted(tiles):
        if s in label:
            continue
        for t in distances(tiles, [s], steps):
            label[t] = n
        n += 1
    return label

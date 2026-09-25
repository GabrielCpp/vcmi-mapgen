"""Detection of open ground that vegetation walled off from every walkable anchor."""

from __future__ import annotations

from collections.abc import Collection
from collections.abc import Set as AbstractSet

from vcmi_mapgen.models import Tile


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
        comp = {start}
        stack = [start]
        seen.add(start)
        while stack:
            x, y = stack.pop()
            for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if n in open_tiles and n not in seen:
                    seen.add(n)
                    comp.add(n)
                    stack.append(n)
        if not comp & anchor_zone:
            islands.append(comp)
    return islands

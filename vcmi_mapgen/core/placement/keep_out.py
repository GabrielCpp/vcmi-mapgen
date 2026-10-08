"""The tiles kept clear of every object: an object is refused when any cell of its
footprint covers one of them."""

from __future__ import annotations

from collections.abc import Iterable
from typing import final

from vcmi_mapgen.core.model import CoverIndex, PlacedObject, Tile
from vcmi_mapgen.core.placement import footprint as FP


@final
class KeepOutRule:
    """The kept-out tiles of one level, as a placement rule."""

    def __init__(self, tiles: Iterable[Tile] = ()) -> None:
        self._tiles: frozenset[Tile] = frozenset(tiles)

    def refuses(self, covers: CoverIndex, obj: PlacedObject) -> list[str]:
        del covers
        hit = sorted(
            (cx, cy)
            for cx, cy, _b in FP.anchored_cells(obj.footprint, obj.x, obj.y)
            if (cx, cy) in self._tiles
        )
        return [f"{obj.kind} stands in a loot zone at {hit[0]}"] if hit else []

from collections.abc import Iterator
from dataclasses import dataclass
from typing import final

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import PlacedObject, Tile
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.placement.footprint import anchored_cells


@dataclass(frozen=True, slots=True)
class TerrainViolation:
    obj: PlacedObject
    tile: Tile
    terrain: str


def footprint_violations(
    catalog: Catalog, grid: list[list[Terrain]], obj: PlacedObject
) -> Iterator[TerrainViolation]:
    if not obj.kind:
        return
    for tx, ty, _blocking in anchored_cells(obj.footprint.solid(), obj.x, obj.y):
        if not (0 <= ty < len(grid) and 0 <= tx < len(grid[ty])):
            continue
        code = grid[ty][tx]
        if not catalog.allowed_on(obj.kind, code):
            yield TerrainViolation(obj, (tx, ty), catalog.terrain_name(code) or str(code))


@final
class TerrainGate:
    def __init__(self, catalog: Catalog) -> None:
        self._catalog = catalog

    def check(self, obj: PlacedObject, terrain: dict[int, list[list[Terrain]]]) -> list[str]:
        grid = terrain.get(obj.level)
        if grid is None:
            return []
        return [
            f"{obj.kind} at {v.tile} on {v.terrain}"
            for v in footprint_violations(self._catalog, grid, obj)
        ]

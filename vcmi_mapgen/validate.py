from collections.abc import Iterator
from dataclasses import dataclass
from typing import final

from vcmi_mapgen.kit.objects import mask_cells
from vcmi_mapgen.models import Cell, MapState, PlacedObject, Tile
from vcmi_mapgen.ontology import TERRAIN_NAMES, Ontology


@dataclass(frozen=True, slots=True)
class TerrainViolation:
    obj: PlacedObject
    tile: Tile
    terrain: str


def footprint_violations(
    ontology: Ontology, grid: list[list[Cell]], obj: PlacedObject
) -> Iterator[TerrainViolation]:
    if not obj.animation:
        return
    solid = tuple(row.replace("V", " ") for row in obj.mask)
    for tx, ty, _blocking in mask_cells(solid, obj.x, obj.y):
        if not (0 <= ty < len(grid) and 0 <= tx < len(grid[ty])):
            continue
        code = grid[ty][tx].t
        if not ontology.allowed_on(obj.animation, code):
            yield TerrainViolation(obj, (tx, ty), TERRAIN_NAMES.get(code, str(code)))


def terrain_violations(ontology: Ontology, state: MapState) -> Iterator[TerrainViolation]:
    for obj in state.objs:
        grid = state.cells.get(obj.level)
        if grid is not None:
            yield from footprint_violations(ontology, grid, obj)


@final
class TerrainGate:
    def __init__(self, ontology: Ontology) -> None:
        self._ontology = ontology

    def check(self, obj: PlacedObject, cells: dict[int, list[list[Cell]]]) -> list[str]:
        grid = cells.get(obj.level)
        if grid is None:
            return []
        return [
            f"{obj.animation} at {v.tile} on {v.terrain}"
            for v in footprint_violations(self._ontology, grid, obj)
        ]

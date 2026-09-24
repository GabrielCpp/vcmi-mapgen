"""MapState — the render-only view of a finished VCMI map."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from vcmi_mapgen.models.objects import Cell, PlacedObject, Tile, Zone


class PlacementError(ValueError):
    pass


class PlacementRules(Protocol):
    def check(self, obj: PlacedObject, cells: dict[int, list[list[Cell]]]) -> list[str]: ...


@dataclass
class MapState:
    """The narrow, render-only view of a finished map: exactly what PngRenderer,
    MapOverlay and VmapRenderer read, and nothing else.

    A field belongs here only if it describes the map itself as VCMI means it --
    terrain, zone segmentation, gate-blocked tiles, placed objects, player towns. It is
    never a count, an analysis, or anything else *derived from* the map at some point in
    the pipeline (see this package's AGENTS.md) -- that kind of data lives in the
    pipeline's ctx dict instead, and reaches a renderer/overlay through its own
    constructor, never through MapState.
    """

    size: int = 72
    surfs: dict[int, list[list[str]]] = field(default_factory=dict)
    cells: dict[int, list[list[Cell]]] = field(default_factory=dict)
    zones: dict[int, dict[int, Zone]] = field(default_factory=dict)
    gate_blk: dict[int, frozenset[Tile]] = field(default_factory=dict)
    objs: list[PlacedObject] = field(default_factory=list)
    player_towns: list[PlacedObject] = field(default_factory=list)

    def place(self, obj: PlacedObject, rules: PlacementRules) -> None:
        self.set_objs([*self.objs, obj], rules)

    def set_objs(self, objs: list[PlacedObject], rules: PlacementRules) -> None:
        for obj in objs:
            problems = rules.check(obj, self.cells)
            if problems:
                raise PlacementError("; ".join(problems))
        self.objs = objs

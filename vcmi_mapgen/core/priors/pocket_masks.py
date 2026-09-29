from dataclasses import dataclass

from vcmi_mapgen.core.model import Tile


@dataclass(frozen=True, slots=True)
class PocketMask:
    name: str
    cells: tuple[tuple[int, int, bool], ...]
    free: frozenset[Tile]
    walls_by_guard: int

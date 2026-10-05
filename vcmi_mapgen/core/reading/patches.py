"""Patches of one level: same-terrain land components of 20 to 150 tiles that one other
land terrain encloses. The reader counts how much of each patch decoration covers and what
counted objects stand in it, the same way on a corpus map and on a generated one."""

import collections
from collections.abc import Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.grid.reach import STEPS4
from vcmi_mapgen.core.model import MapState, PlacedObject, Tile, footprint
from vcmi_mapgen.core.model.purpose import COUNTED, Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.reading.paint import components

MIN_TILES = 20
MAX_TILES = 150
ENCLOSED = 0.7


@dataclass(frozen=True, slots=True)
class Patch:
    """One patch: its terrain, its tile count, the share of its tiles decoration covers,
    and the purpose of each counted object inside it."""

    terrain: Terrain
    tiles: int
    cover: float
    content: tuple[str, ...]


def _decorative(obj: PlacedObject) -> bool:
    return obj.purpose in ("", Purpose.DECORATION)


def _decor_tiles(objs: Sequence[PlacedObject]) -> set[Tile]:
    return {
        tile
        for o in objs
        if _decorative(o)
        for tile, role in footprint(o)
        if role.blocks or role.interactive
    }


def _enclosed(comp: set[Tile], grid: Sequence[Sequence[Terrain]]) -> bool:
    h, w = len(grid), len(grid[0])
    rim: collections.Counter[Terrain] = collections.Counter()
    for x, y in comp:
        for dx, dy in STEPS4:
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in comp:
                rim[grid[ny][nx]] += 1
    if not rim:
        return False
    top, count = rim.most_common(1)[0]
    return top.is_land and count >= ENCLOSED * rim.total()


def _inside(obj: PlacedObject, comp: set[Tile]) -> bool:
    if (obj.x, obj.y) in comp:
        return True
    return any(role.interactive and tile in comp for tile, role in footprint(obj))


def read_patches(map_state: MapState, level: int) -> list[Patch]:
    """Every patch of ``level`` with its decoration cover and its counted objects."""
    grid = map_state.terrain.get(level)
    if not grid:
        return []
    objs = map_state.objs_by_level([level]).get(level, [])
    decor = _decor_tiles(objs)
    counted = [o for o in objs if o.purpose in COUNTED]
    terrain = {(x, y): t for y, row in enumerate(grid) for x, t in enumerate(row) if t.is_land}
    out: list[Patch] = []
    for comp in components(terrain, terrain):
        if not MIN_TILES <= len(comp) <= MAX_TILES:
            continue
        tiles = set(comp)
        if not _enclosed(tiles, grid):
            continue
        cover = sum(1 for t in comp if t in decor) / len(comp)
        content = tuple(sorted(str(o.purpose) for o in counted if _inside(o, tiles)))
        out.append(Patch(terrain[comp[0]], len(comp), cover, content))
    return out


def map_cover(map_state: MapState, level: int) -> float | None:
    """The share of the land of ``level`` that decoration covers, or None without land."""
    grid = map_state.terrain.get(level)
    if not grid:
        return None
    land = [(x, y) for y, row in enumerate(grid) for x, t in enumerate(row) if t.is_land]
    if not land:
        return None
    decor = _decor_tiles(map_state.objs_by_level([level]).get(level, []))
    return sum(1 for t in land if t in decor) / len(land)

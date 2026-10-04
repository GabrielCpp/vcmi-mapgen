"""What place inference reads from one level of a map: the land, the walkable tiles, the
guards' zones of control, the towns and the reward objects, as plain tile sets."""

from collections.abc import Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState, PlacedObject, Tile, footprint
from vcmi_mapgen.core.model.purpose import COUNTED, Purpose
from vcmi_mapgen.core.model.terrain import Terrain

REWARD_PURPOSES = frozenset(
    {*COUNTED, Purpose.RESOURCE_PILE, Purpose.REWARD_PICKUP} - {Purpose.TOWN}
)

type TownKey = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class TownSite:
    """A town by its anchor position ``(x, y, level)`` and every tile it covers."""

    key: TownKey
    cells: tuple[Tile, ...]


@dataclass(frozen=True, slots=True)
class Ground:
    """One level read for place inference. ``walk`` is the land minus every blocking
    footprint cell and gate-blocked tile. ``zoc`` is the walkable part of the Chebyshev-1
    ring around every guard's interactive cells. ``rewards`` holds one tile per reward
    object."""

    width: int
    height: int
    terrain: Sequence[Sequence[Terrain]]
    land: frozenset[Tile]
    walk: frozenset[Tile]
    zoc: frozenset[Tile]
    towns: tuple[TownSite, ...]
    rewards: tuple[Tile, ...]

    @property
    def blocked(self) -> frozenset[Tile]:
        """The land tiles a hero cannot stand on."""
        return self.land - self.walk

    def inside(self, t: Tile) -> bool:
        return 0 <= t[0] < self.width and 0 <= t[1] < self.height


def purpose_of(catalog: Catalog, obj: PlacedObject) -> str:
    """The object's own purpose, or the catalog's when the object carries none."""
    if obj.purpose and obj.purpose != Purpose.UNKNOWN:
        return obj.purpose
    spec = catalog.spec(obj.kind)
    if spec is not None and spec.purpose is not None:
        return spec.purpose
    return obj.purpose


def _interactive(obj: PlacedObject) -> list[Tile]:
    return [t for t, role in obj.footprint.at(obj.x, obj.y) if role.interactive]


def _ring(cells: Sequence[Tile]) -> set[Tile]:
    return {(x + dx, y + dy) for x, y in cells for dx in (-1, 0, 1) for dy in (-1, 0, 1)}


def _reward_tile(obj: PlacedObject) -> Tile:
    cells = sorted(_interactive(obj))
    return cells[0] if cells else (obj.x, obj.y)


def read_ground(catalog: Catalog, map_state: MapState, level: int) -> Ground | None:
    """The ground of ``level``, or None when the map has no such level."""
    terrain = map_state.terrain.get(level)
    if not terrain or not terrain[0]:
        return None
    land = frozenset(
        (x, y) for y, row in enumerate(terrain) for x, t in enumerate(row) if t.is_land
    )
    blocked = set(map_state.gate_blk.get(level, frozenset()))
    guards: list[Tile] = []
    towns: list[TownSite] = []
    rewards: list[Tile] = []
    for obj in map_state.objs_by_level([level])[level]:
        blocked.update(t for t, role in obj.footprint.at(obj.x, obj.y) if role.blocks)
        purpose = purpose_of(catalog, obj)
        if purpose == Purpose.GUARD:
            guards.extend(_interactive(obj))
        elif purpose == Purpose.TOWN:
            cells = tuple(sorted({t for t, _ in footprint(obj)}))
            towns.append(TownSite((obj.x, obj.y, obj.level), cells))
        elif purpose in REWARD_PURPOSES:
            rewards.append(_reward_tile(obj))
    walk = land - blocked
    return Ground(
        width=len(terrain[0]),
        height=len(terrain),
        terrain=terrain,
        land=land,
        walk=walk,
        zoc=frozenset(_ring(guards) & walk),
        towns=tuple(sorted(towns, key=lambda s: s.key)),
        rewards=tuple(rewards),
    )

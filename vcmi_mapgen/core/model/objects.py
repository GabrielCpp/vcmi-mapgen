from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import NamedTuple

from vcmi_mapgen.core.model.payload import Payload
from vcmi_mapgen.core.model.terrain import Terrain

type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None
type Tile = tuple[int, int]
type ObjectKind = str


class Role(StrEnum):
    BLOCKING = "blocking"
    ENTRANCE = "entrance"
    VISIT = "visit"
    OVERLAY = "overlay"
    APPROACH = "approach"

    @property
    def blocks(self) -> bool:
        return self in (Role.BLOCKING, Role.ENTRANCE)

    @property
    def interactive(self) -> bool:
        return self in (Role.ENTRANCE, Role.VISIT)


@dataclass(frozen=True, slots=True)
class Footprint:
    """The cells an object covers, as (dx, dy, role) offsets from its anchor. The anchor is
    the bottom-right cell of a `width` by `height` box, so every offset is zero or negative.
    Cells run row by row from the top-left."""

    width: int
    height: int
    cells: tuple[tuple[int, int, Role], ...]

    @classmethod
    def one(cls, role: Role) -> Footprint:
        return cls(1, 1, ((0, 0, role),))

    def at(self, x: int, y: int) -> Iterator[tuple[Tile, Role]]:
        for dx, dy, role in self.cells:
            yield (x + dx, y + dy), role

    def solid(self) -> Footprint:
        """This footprint without its overlay cells."""
        cells = tuple(c for c in self.cells if c[2] is not Role.OVERLAY)
        return Footprint(self.width, self.height, cells)

    def grid(self) -> tuple[tuple[Role | None, ...], ...]:
        """The `height` by `width` box row by row, with None where no cell is."""
        rows: list[list[Role | None]] = [[None] * self.width for _ in range(self.height)]
        for dx, dy, role in self.cells:
            rows[self.height - 1 + dy][self.width - 1 + dx] = role
        return tuple(tuple(r) for r in rows)


class Entrance(NamedTuple):
    rep: Tile
    band: frozenset[Tile]
    other: int


@dataclass(frozen=True, slots=True)
class Identity:
    type: str | None
    subtype: str | None
    kind: ObjectKind
    footprint: Footprint


@dataclass(slots=True)
class PlacedObject:
    x: int
    y: int
    level: int
    purpose: str
    kind: ObjectKind
    footprint: Footprint
    payload: Payload | None = None
    seal: bool = False
    cache: bool = False
    pocket_guard: bool = False

    @classmethod
    def at(
        cls,
        identity: Identity,
        tile: Tile,
        *,
        level: int = 0,
        purpose: str,
        payload: Payload | None = None,
    ) -> PlacedObject:
        return cls(
            x=tile[0],
            y=tile[1],
            level=level,
            purpose=purpose,
            kind=identity.kind,
            footprint=identity.footprint,
            payload=payload,
        )


@dataclass(slots=True)
class Zone:
    terrain_type: Terrain
    area: int
    centroid: tuple[float, float]
    tiles: list[Tile]
    tiles_set: frozenset[Tile]
    boundary_tiles: set[Tile] = field(default_factory=set)
    chokepoints: set[Tile] = field(default_factory=set)
    adjacent_zones: set[int] = field(default_factory=set)

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple

type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None
type Tile = tuple[int, int]
type Mask = tuple[str, ...]


class Entrance(NamedTuple):
    rep: Tile
    band: frozenset[Tile]
    other: int


@dataclass(frozen=True, slots=True)
class Identity:
    type: str | None
    subtype: str | None
    animation: str
    mask: Mask


@dataclass(slots=True)
class PlacedObject:
    x: int
    y: int
    level: int
    purpose: str
    type: str | None
    subtype: str | None
    animation: str
    mask: Mask
    options: dict[str, JsonValue] | None = None
    visitable_from: tuple[str, ...] | None = None
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
        options: dict[str, JsonValue] | None = None,
    ) -> PlacedObject:
        return cls(
            x=tile[0],
            y=tile[1],
            level=level,
            purpose=purpose,
            type=identity.type,
            subtype=identity.subtype,
            animation=identity.animation,
            mask=identity.mask,
            options=options,
        )


@dataclass(frozen=True, slots=True)
class Cell:
    t: int
    view: int = 0
    m: int = 0
    rt: int = 0
    rd: int = 0
    ot: int = 0
    od: int = 0


@dataclass(slots=True)
class Zone:
    terrain_type: int
    area: int
    centroid: tuple[float, float]
    tiles: list[Tile]
    tiles_set: frozenset[Tile]
    boundary_tiles: set[Tile] = field(default_factory=set)
    chokepoints: set[Tile] = field(default_factory=set)
    adjacent_zones: set[int] = field(default_factory=set)

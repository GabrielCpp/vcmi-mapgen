"""MapState — the map as a grid of tiles, plus the objects standing on it."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from vcmi_mapgen.models.objects import Cell, PlacedObject, Tile, Zone


class Role(StrEnum):
    BLOCKING = "B"
    ENTRANCE = "X"
    VISIT = "A"
    OVERLAY = "V"
    APPROACH = "approach"


@dataclass(frozen=True, slots=True)
class Cover:
    obj: PlacedObject
    role: Role

    @property
    def blocking(self) -> bool:
        return self.role in (Role.BLOCKING, Role.ENTRANCE)

    @property
    def interactive(self) -> bool:
        return self.role in (Role.VISIT, Role.ENTRANCE, Role.APPROACH)


@dataclass(frozen=True, slots=True)
class TileView:
    """Everything the map knows about one tile. ``border`` marks the sentinel returned for a
    position outside the map, which is always blocking."""

    level: int
    x: int
    y: int
    terrain: int | None
    zone: int | None
    gate_blocked: bool
    covers: tuple[Cover, ...]
    border: bool = False

    @property
    def blocking(self) -> bool:
        return self.border or self.gate_blocked or any(c.blocking for c in self.covers)

    @property
    def visitable(self) -> bool:
        return any(c.role in (Role.VISIT, Role.ENTRANCE) for c in self.covers)

    @property
    def approach(self) -> bool:
        return any(c.role is Role.APPROACH for c in self.covers)

    @property
    def overlay(self) -> bool:
        return any(c.role is Role.OVERLAY for c in self.covers)

    @property
    def free(self) -> bool:
        return not (self.blocking or self.visitable or self.approach)


BORDER = TileView(
    level=-1, x=-1, y=-1, terrain=None, zone=None, gate_blocked=False, covers=(), border=True
)


def footprint(obj: PlacedObject) -> list[tuple[Tile, Role]]:
    """Every tile an object covers, with its role. The anchor is the bottom-right cell of the
    mask. An entrance ('X') also claims the tile below it as its approach."""
    out: list[tuple[Tile, Role]] = []
    hh = len(obj.mask)
    for r, row in enumerate(obj.mask):
        ww = len(row)
        for c, ch in enumerate(row):
            if ch == " ":
                continue
            tile = (obj.x - (ww - 1 - c), obj.y - (hh - 1 - r))
            out.append((tile, Role(ch)))
            if ch == "X":
                out.append(((tile[0], tile[1] + 1), Role.APPROACH))
    return out


def index_of(objs: list[PlacedObject]) -> dict[tuple[int, Tile], list[Cover]]:
    index: dict[tuple[int, Tile], list[Cover]] = {}
    for obj in objs:
        for tile, role in footprint(obj):
            index.setdefault((obj.level, tile), []).append(Cover(obj, role))
    return index


def covering_problems(obj: PlacedObject, index: dict[tuple[int, Tile], list[Cover]]) -> list[str]:
    """Reasons ``obj`` cannot stand where it is: any of its tiles on another object's visit,
    entrance or approach tile. A guard stands on an approach tile and its sprite overlays the
    entrance, since that is its job."""
    problems: list[str] = []
    for tile, role in footprint(obj):
        if role is Role.APPROACH or (obj.purpose == "GUARD" and role is Role.OVERLAY):
            continue
        for cover in index.get((obj.level, tile), ()):
            if cover.obj is obj or not cover.interactive:
                continue
            if obj.purpose == "GUARD" and cover.role is Role.APPROACH:
                continue
            problems.append(
                f"{obj.animation} at {tile} covers the {cover.role.name.lower()} tile"
                + f" of {cover.obj.animation}"
            )
    return problems


def evict_conflicts(objs: list[PlacedObject]) -> tuple[list[PlacedObject], list[PlacedObject]]:
    """Split ``objs`` into those that may stay and those whose tiles cover another object's
    visit, entrance or approach tile. Each round evicts every offender, so two objects that
    cover each other both go."""
    kept = list(objs)
    evicted: list[PlacedObject] = []
    while True:
        index = index_of(kept)
        bad = {id(o) for o in kept if covering_problems(o, index)}
        if not bad:
            return kept, evicted
        evicted.extend(o for o in kept if id(o) in bad)
        kept = [o for o in kept if id(o) not in bad]


class PlacementError(ValueError):
    pass


class PlacementRules(Protocol):
    def check(self, obj: PlacedObject, cells: dict[int, list[list[Cell]]], /) -> list[str]: ...


@dataclass
class MapState:
    """The map as VCMI means it: a ``size`` by ``size`` grid on each level, with terrain
    (``surfs``/``cells``), zone segmentation (``zones``), gate-blocked tiles (``gate_blk``),
    placed objects (``objs``) and player towns (``player_towns``).

    Ask about a tile with ``at``. A position outside the map answers ``BORDER``, a blocking
    sentinel. Ask about an object with ``free_for`` before placing it.

    Anything derived from the map at one point in a run (reachability, pockets, scores)
    is not a map fact and lives in the pipeline's ctx instead.
    """

    size: int
    surfs: dict[int, list[list[str]]] = field(default_factory=dict)
    cells: dict[int, list[list[Cell]]] = field(default_factory=dict)
    zones: dict[int, dict[int, Zone]] = field(default_factory=dict)
    gate_blk: dict[int, frozenset[Tile]] = field(default_factory=dict)
    objs: list[PlacedObject] = field(default_factory=list)
    player_towns: list[PlacedObject] = field(default_factory=list)
    _covers: dict[tuple[int, Tile], list[Cover]] = field(
        default_factory=dict, init=False, repr=False
    )
    _covers_of: tuple[int, int] | None = field(default=None, init=False, repr=False)
    _zone_of: dict[tuple[int, Tile], int] = field(default_factory=dict, init=False, repr=False)
    _zone_key: int | None = field(default=None, init=False, repr=False)

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.size and 0 <= y < self.size

    def _covers_index(self) -> dict[tuple[int, Tile], list[Cover]]:
        key = (id(self.objs), len(self.objs))
        if self._covers_of != key:
            self._covers = index_of(self.objs)
            self._covers_of = key
        return self._covers

    def _zone_index(self) -> dict[tuple[int, Tile], int]:
        if self._zone_key != id(self.zones):
            self._zone_of = {
                (level, tile): zid
                for level, zs in self.zones.items()
                for zid, z in zs.items()
                for tile in z.tiles_set
            }
            self._zone_key = id(self.zones)
        return self._zone_of

    def covers_at(self, level: int, x: int, y: int) -> tuple[Cover, ...]:
        return tuple(self._covers_index().get((level, (x, y)), ()))

    def at(self, level: int, x: int, y: int) -> TileView:
        if not self.in_bounds(x, y):
            return BORDER
        grid = self.cells.get(level)
        terrain = grid[y][x].t if grid is not None and y < len(grid) and x < len(grid[y]) else None
        return TileView(
            level=level,
            x=x,
            y=y,
            terrain=terrain,
            zone=self._zone_index().get((level, (x, y))),
            gate_blocked=(x, y) in self.gate_blk.get(level, frozenset()),
            covers=self.covers_at(level, x, y),
        )

    def taken_tiles(self, level: int) -> frozenset[Tile]:
        """Every tile of a level covered by an object or gate-blocked."""
        return frozenset(
            tile for (lvl, tile) in self._covers_index() if lvl == level
        ) | self.gate_blk.get(level, frozenset())

    def conflicts(self, obj: PlacedObject) -> list[str]:
        return covering_problems(obj, self._covers_index())

    def place(self, obj: PlacedObject, rules: PlacementRules) -> None:
        self.set_objs([*self.objs, obj], rules)

    def settle(self, objs: list[PlacedObject], rules: PlacementRules) -> list[PlacedObject]:
        """Write ``objs`` after evicting every object that covers another object's interactive
        tile. Returns the evicted objects."""
        kept, evicted = evict_conflicts(objs)
        self.set_objs(kept, rules)
        return evicted

    def set_objs(self, objs: list[PlacedObject], rules: PlacementRules) -> None:
        index = index_of(objs)
        for obj in objs:
            problems = rules.check(obj, self.cells) + covering_problems(obj, index)
            if problems:
                raise PlacementError("; ".join(problems))
        self.objs = objs

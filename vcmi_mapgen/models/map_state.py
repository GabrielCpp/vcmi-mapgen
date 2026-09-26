"""MapState — the map as a grid of tiles, plus the objects standing on it."""

from __future__ import annotations

from collections.abc import Iterable
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


_PICKUPS = frozenset({"RESOURCE_PILE", "REWARD_PICKUP"})


def _clash(culprit: PlacedObject, role: Role, tile: Tile, victim: Cover) -> str | None:
    """Why ``culprit``, covering ``tile`` with ``role``, may not share it with ``victim``. Only
    another object's visit, entrance or approach tile is protected. A guard stands on an
    approach tile and its sprite overlays the entrance, since that is its job. A pickup may sit
    partly behind another object's sprite, so an overlay over a pickup is allowed."""
    if role is Role.APPROACH:
        return None
    if role is Role.OVERLAY and (culprit.purpose == "GUARD" or victim.obj.purpose in _PICKUPS):
        return None
    if victim.obj is culprit or not victim.interactive:
        return None
    if culprit.purpose == "GUARD" and victim.role is Role.APPROACH:
        return None
    return (
        f"{culprit.animation} at {tile} covers the {victim.role.name.lower()} tile"
        + f" of {victim.obj.animation}"
    )


def covering_problems(obj: PlacedObject, index: dict[tuple[int, Tile], list[Cover]]) -> list[str]:
    """Reasons ``obj`` cannot stand where it is: any of its tiles on another object's visit,
    entrance or approach tile."""
    problems: list[str] = []
    for tile, role in footprint(obj):
        for cover in index.get((obj.level, tile), ()):
            problem = _clash(obj, role, tile, cover)
            if problem:
                problems.append(problem)
    return problems


class CoverIndex:
    """The tiles of one level that objects cover, kept up to date as a placer adds objects.
    ``conflicts`` answers both ways: ``obj`` covering another object's interactive tile, and
    another object covering an interactive tile of ``obj``."""

    def __init__(self, objs: Iterable[PlacedObject] = ()) -> None:
        self._at: dict[Tile, list[Cover]] = {}
        for obj in objs:
            self.add(obj)

    def add(self, obj: PlacedObject) -> None:
        for tile, role in footprint(obj):
            self._at.setdefault(tile, []).append(Cover(obj, role))

    def reset(self, objs: Iterable[PlacedObject]) -> None:
        self._at.clear()
        for obj in objs:
            self.add(obj)

    def conflicts(self, obj: PlacedObject) -> list[str]:
        problems: list[str] = []
        for tile, role in footprint(obj):
            for cover in self._at.get(tile, ()):
                if cover.obj is obj:
                    continue
                for problem in (
                    _clash(obj, role, tile, cover),
                    _clash(cover.obj, cover.role, tile, Cover(obj, role)),
                ):
                    if problem:
                        problems.append(problem)
        return problems

    def accepts(self, obj: PlacedObject) -> bool:
        return not self.conflicts(obj)

    def try_add(self, obj: PlacedObject) -> bool:
        if self.conflicts(obj):
            return False
        self.add(obj)
        return True


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
        self.add_objs([obj], rules)

    def add_objs(self, new: list[PlacedObject], rules: PlacementRules) -> None:
        """Append ``new`` to the map. Only the new objects are checked: each against the
        terrain rules, and each against every other object in both directions. The objects
        already on the map stay as they are."""
        objs = [*self.objs, *new]
        index = index_of(objs)
        problems: list[str] = []
        for obj in new:
            problems += rules.check(obj, self.cells) + covering_problems(obj, index)
            for tile, role in footprint(obj):
                for cover in index.get((obj.level, tile), ()):
                    if cover.obj is obj:
                        continue
                    problem = _clash(cover.obj, cover.role, tile, Cover(obj, role))
                    if problem:
                        problems.append(problem)
        if problems:
            raise PlacementError("; ".join(problems))
        self.objs = objs

    def set_objs(self, objs: list[PlacedObject], rules: PlacementRules) -> None:
        index = index_of(objs)
        for obj in objs:
            problems = rules.check(obj, self.cells) + covering_problems(obj, index)
            if problems:
                raise PlacementError("; ".join(problems))
        self.objs = objs

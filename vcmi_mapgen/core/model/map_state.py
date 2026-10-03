"""MapState — the map as a grid of tiles, plus the objects standing on it."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from typing import Protocol

from vcmi_mapgen.core.model.objects import PlacedObject, Role, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain


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
    terrain: Terrain | None
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


BORDER = TileView(level=-1, x=-1, y=-1, terrain=None, gate_blocked=False, covers=(), border=True)


def footprint(obj: PlacedObject) -> list[tuple[Tile, Role]]:
    """Every tile an object covers, with its role. An entrance also claims the tile below it
    as its approach."""
    out: list[tuple[Tile, Role]] = []
    for tile, role in obj.footprint.at(obj.x, obj.y):
        out.append((tile, role))
        if role is Role.ENTRANCE:
            out.append(((tile[0], tile[1] + 1), Role.APPROACH))
    return out


def index_of(objs: list[PlacedObject]) -> dict[tuple[int, Tile], list[Cover]]:
    index: dict[tuple[int, Tile], list[Cover]] = {}
    for obj in objs:
        for tile, role in footprint(obj):
            index.setdefault((obj.level, tile), []).append(Cover(obj, role))
    return index


_BEHIND_SPRITES = frozenset({Purpose.RESOURCE_PILE, Purpose.REWARD_PICKUP, Purpose.GUARD})
_DECOR = frozenset({"", Purpose.DECORATION})
_DOOR = frozenset({Role.ENTRANCE, Role.APPROACH})


def _clash(culprit: PlacedObject, role: Role, tile: Tile, victim: Cover) -> str | None:
    """Why ``culprit``, covering ``tile`` with ``role``, may not share it with ``victim``. Only
    another object's visit, entrance or approach tile is protected. A guard stands on an
    approach tile and its sprite overlays the entrance, since that is its job. A pickup or a
    guard may sit partly behind another object's sprite, so an overlay over either is allowed.
    A decoration's sprite may overhang an entrance or its approach, as it does on most corpus
    maps, but never a walk-on visit tile."""
    if role is Role.APPROACH:
        return None
    if role is Role.OVERLAY and culprit.purpose in _DECOR and victim.role in _DOOR:
        return None
    if role is Role.OVERLAY and (
        culprit.purpose == Purpose.GUARD or victim.obj.purpose in _BEHIND_SPRITES
    ):
        return None
    if victim.obj is culprit or not victim.interactive:
        return None
    if culprit.purpose == Purpose.GUARD and victim.role is Role.APPROACH:
        return None
    return (
        f"{culprit.kind} at {tile} covers the {victim.role.name.lower()} tile"
        + f" of {victim.obj.kind}"
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


class PlacementRule(Protocol):
    """A reason a candidate may not stand where it is, read from the covers of its level."""

    def refuses(self, covers: CoverIndex, obj: PlacedObject) -> list[str]: ...


class CoverIndex:
    """The tiles of one level that objects cover, and the tiles placers have claimed, kept up
    to date as a placer adds objects. ``conflicts`` answers both ways: ``obj`` covering another
    object's interactive tile, and another object covering an interactive tile of ``obj``.
    It then asks each of ``rules``. ``mark`` and ``rollback`` undo every object added and every
    tile claimed since the mark."""

    def __init__(
        self,
        objs: Iterable[PlacedObject] = (),
        claims: Iterable[Tile] = (),
        rules: Sequence[PlacementRule] = (),
    ) -> None:
        self._at: dict[Tile, list[Cover]] = {}
        self._claimed: set[Tile] = set(claims)
        self._log: list[PlacedObject | frozenset[Tile]] = []
        self._rules: tuple[PlacementRule, ...] = tuple(rules)
        for obj in objs:
            self.add(obj)

    @property
    def claims(self) -> AbstractSet[Tile]:
        return self._claimed

    def covers_at(self, tile: Tile) -> Sequence[Cover]:
        return self._at.get(tile, ())

    def add(self, obj: PlacedObject) -> None:
        for tile, role in footprint(obj):
            self._at.setdefault(tile, []).append(Cover(obj, role))
        self._log.append(obj)

    def claim(self, cells: Iterable[Tile]) -> None:
        fresh = frozenset(cells) - self._claimed
        self._claimed |= fresh
        self._log.append(fresh)

    def mark(self) -> int:
        return len(self._log)

    def rollback(self, mark: int) -> None:
        while len(self._log) > mark:
            entry = self._log.pop()
            if isinstance(entry, frozenset):
                self._claimed -= entry
                continue
            for tile, _role in footprint(entry):
                kept = [c for c in self._at[tile] if c.obj is not entry]
                if kept:
                    self._at[tile] = kept
                else:
                    del self._at[tile]

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
        for rule in self._rules:
            problems += rule.refuses(self, obj)
        return problems

    def accepts(self, obj: PlacedObject) -> bool:
        return not self.conflicts(obj)

    def try_add(self, obj: PlacedObject) -> bool:
        if self.conflicts(obj):
            return False
        self.add(obj)
        return True

    def try_claim(self, obj: PlacedObject, cells: Iterable[Tile]) -> bool:
        if not self.try_add(obj):
            return False
        self.claim(cells)
        return True


class PlacementError(ValueError):
    pass


@dataclass
class MapState:
    """The map as VCMI means it: a ``size`` by ``size`` grid on each level, with terrain
    (``terrain``, one ``Terrain`` per tile after despeckle), gate-blocked tiles
    (``gate_blk``), placed objects (``objs``) and player towns (``player_towns``).

    Ask about a tile with ``at``. A position outside the map answers ``BORDER``, a blocking
    sentinel. Ask about an object with ``free_for`` before placing it.

    Anything derived from the map at one point in a run (reachability, pockets, scores)
    is not a map fact and lives in the pipeline's ctx instead.
    """

    size: int
    terrain: dict[int, list[list[Terrain]]] = field(default_factory=dict)
    gate_blk: dict[int, frozenset[Tile]] = field(default_factory=dict)
    objs: list[PlacedObject] = field(default_factory=list)
    player_towns: list[PlacedObject] = field(default_factory=list)
    _covers: dict[tuple[int, Tile], list[Cover]] = field(
        default_factory=dict, init=False, repr=False
    )
    _covers_of: tuple[int, int] | None = field(default=None, init=False, repr=False)

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.size and 0 <= y < self.size

    def _covers_index(self) -> dict[tuple[int, Tile], list[Cover]]:
        key = (id(self.objs), len(self.objs))
        if self._covers_of != key:
            self._covers = index_of(self.objs)
            self._covers_of = key
        return self._covers

    def covers_at(self, level: int, x: int, y: int) -> tuple[Cover, ...]:
        return tuple(self._covers_index().get((level, (x, y)), ()))

    def at(self, level: int, x: int, y: int) -> TileView:
        if not self.in_bounds(x, y):
            return BORDER
        grid = self.terrain.get(level)
        terrain = grid[y][x] if grid is not None and y < len(grid) and x < len(grid[y]) else None
        return TileView(
            level=level,
            x=x,
            y=y,
            terrain=terrain,
            gate_blocked=(x, y) in self.gate_blk.get(level, frozenset()),
            covers=self.covers_at(level, x, y),
        )

    def objs_by_level(self, levels: Iterable[int]) -> dict[int, list[PlacedObject]]:
        """A fresh list for each of ``levels`` holding the objects on that level, in the
        order they were placed."""
        by_level: dict[int, list[PlacedObject]] = {lvl: [] for lvl in levels}
        for o in self.objs:
            if o.level in by_level:
                by_level[o.level].append(o)
        return by_level

    def taken_tiles(self, level: int) -> frozenset[Tile]:
        """Every tile of a level covered by an object or gate-blocked."""
        return frozenset(
            tile for (lvl, tile) in self._covers_index() if lvl == level
        ) | self.gate_blk.get(level, frozenset())

    def conflicts(self, obj: PlacedObject) -> list[str]:
        return covering_problems(obj, self._covers_index())

    def place(self, obj: PlacedObject) -> None:
        self.add_objs([obj])

    def add_objs(self, new: list[PlacedObject]) -> None:
        """Append ``new`` to the map. Only the new objects are checked, each against every
        other object in both directions. The objects already on the map stay as they are."""
        objs = [*self.objs, *new]
        index = index_of(objs)
        problems: list[str] = []
        for obj in new:
            problems += covering_problems(obj, index)
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

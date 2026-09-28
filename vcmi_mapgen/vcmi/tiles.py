"""Tile art: which picture each tile of a terrain grid shows.

A `Cell` is one tile as VCMI draws it: the terrain, the frame (`view`), the mirror flag
(`m`) and any river or road. `tile` gives each tile of a `Terrain` grid the frame and flip
the corpus maps use for the same terrain with the same eight neighbours, so shores, beaches
and land-land blends come out as the editor draws them. It backs off from the exact eight
neighbours to the four orthogonal ones, then to a clean interior frame. Tiling draws no
random number, so the exported map and the PNG render show the same art.

`THIN_DRAWABLE` names the terrains whose tilesets can draw a shape one tile wide. Terrain
generation passes it to despeckle, which erodes one-wide shapes of every other terrain.
"""

from __future__ import annotations

import collections
import re
from collections.abc import Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.vcmi.terrain import BY_PREFIX, prefix_of

type ViewMirror = tuple[int, int]
type SigTable = dict[tuple[int, tuple[int, ...]], collections.Counter[ViewMirror]]

THIN_DRAWABLE: frozenset[Terrain] = frozenset({Terrain.DIRT, Terrain.SAND, Terrain.SUBTERRANEAN})
"""Dirt and sand are the base terrains: the neighbour draws the transition on its own tile,
so a base tile always renders clean. Subterranean is the tunnel terrain, and real
undergrounds are full of one-wide tunnels. The corpus shares of interior tiles in no 2x2
square of their own terrain are dirt 0.065%, sand 0.59% and subterranean 0.45%, against
about 0.00% for every other terrain, whose unseen one-wide signatures would render as an
abrupt untransitioned square."""

CLEAN_VIEWS: dict[int, list[int]] = {
    0: [21, 22, 23, 24, 25, 26, 27, 28, 29],
    1: [0, 1, 2, 3, 4, 5, 6, 7],
    2: [49, 50, 51, 52, 53, 54, 55, 56],
    3: [49, 50, 51, 52, 53, 54, 55, 56],
    4: [49, 50, 51, 52, 53, 54, 55, 56],
    5: [49, 50, 51, 52, 53, 54, 55, 56],
    6: [49, 50, 51, 52, 53, 54, 55, 56],
    7: [49, 50, 51, 52, 53, 54, 55, 56],
    8: [21, 22, 23, 24, 25, 26, 27, 28, 29],
    9: [0, 1, 2, 3, 4, 5, 6, 7],
}
"""Per terrain, the clean interior frames the corpus uses on tiles whose four neighbours
share their terrain. The low frames land on transition art for most terrains, which reads
as patchy ground."""

RIVER = {1: "clrv", 2: "icyrv", 3: "mudrv", 4: "lavrv"}
_RIVER_REV = {v: k for k, v in RIVER.items()}
ROAD = {1: "dirtrd", 2: "gravrd", 3: "cobbrd"}
_ROAD_REV = {v: k for k, v in ROAD.items()}

_TILE_RE = re.compile(
    r"^(?P<t>[a-z]{2})(?P<view>\d+)(?P<mir>[+|_-])"
    + r"(?:(?P<river>clrv|icyrv|mudrv|lavrv)(?P<rd>\d+)_)?"
    + r"(?:(?P<road>dirtrd|gravrd|cobbrd)(?P<od>\d+)_)?$"
)

_N8 = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))


@dataclass(frozen=True, slots=True)
class Cell:
    t: int
    view: int = 0
    m: int = 0
    rt: int = 0
    rd: int = 0
    ot: int = 0
    od: int = 0


@dataclass(frozen=True, slots=True)
class TilerTables:
    """The frames the corpus uses, counted per tile: ``exact`` keyed by terrain and the eight
    neighbour terrains, ``four`` keyed by terrain and the N, W, E, S neighbours, and
    ``clean`` keyed by terrain for tiles whose eight neighbours all share it."""

    exact: SigTable
    four: SigTable
    clean: dict[int, collections.Counter[ViewMirror]]


def neighbours8(grid: Sequence[Sequence[int]], x: int, y: int) -> tuple[int, ...]:
    """The terrains of the eight tiles around ``(x, y)``. A tile off the map reads as the
    centre's own terrain."""
    H, W = len(grid), len(grid[0])
    t = grid[y][x]
    return tuple(
        grid[y + dy][x + dx] if 0 <= x + dx < W and 0 <= y + dy < H else t for dx, dy in _N8
    )


def four_of(sig: tuple[int, ...]) -> tuple[int, ...]:
    return (sig[1], sig[3], sig[4], sig[6])


def _clean_cell(t: int, x: int, y: int) -> Cell:
    vs = CLEAN_VIEWS.get(t, [49, 50, 51, 52, 53, 54, 55, 56])
    return Cell(t=t, view=vs[(x * 7 + y * 13) % len(vs)])


def _tile_cell(t: int, sig: tuple[int, ...], x: int, y: int, tables: TilerTables) -> Cell:
    if all(v == t for v in sig):
        cc = tables.clean.get(t)
        if cc:
            opts = [vm for vm, _ in cc.most_common(8)]
            view, mm = opts[(x * 7 + y * 13) % len(opts)]
            return Cell(t=t, view=view, m=mm)
        return _clean_cell(t, x, y)
    hit = tables.exact.get((t, sig)) or tables.four.get((t, four_of(sig)))
    if not hit:
        return _clean_cell(t, x, y)
    view, mm = hit.most_common(1)[0][0]
    return Cell(t=t, view=view, m=mm)


def tile(terrain: Sequence[Sequence[Terrain]], tables: TilerTables) -> list[list[Cell]]:
    """Each tile of ``terrain`` with the frame and flip the corpus uses for it."""
    grid = [[int(t) for t in row] for row in terrain]
    return [
        [_tile_cell(t, neighbours8(grid, x, y), x, y, tables) for x, t in enumerate(row)]
        for y, row in enumerate(grid)
    ]


def _mir(m: int) -> str:
    h, v = m & 1, m & 2
    return "+" if (h and v) else "|" if v else "-" if h else "_"


def _mir_code(ch: str) -> int:
    return {"+": 3, "|": 2, "-": 1, "_": 0}[ch]


def tile_string(c: Cell) -> str:
    s = f"{prefix_of(c.t)}{c.view}{_mir(c.m)}"
    if c.rt:
        s += f"{RIVER.get(c.rt, 'clrv')}{c.rd}_"
    if c.ot:
        s += f"{ROAD.get(c.ot, 'dirtrd')}{c.od}_"
    return s


def tile_strings(terrain: Sequence[Sequence[Terrain]], tables: TilerTables) -> list[list[str]]:
    return [[tile_string(c) for c in row] for row in tile(terrain, tables)]


def decode_tile_string(s: str) -> Cell:
    """Inverse of `tile_string`: a VCMI tile token -> `Cell(t, view, m, rt, rd, ot, od)`."""
    m = _TILE_RE.match(s)
    if not m:
        raise ValueError(f"not a VCMI tile string: {s!r}")
    river, rd, road, od = m["river"], m["rd"], m["road"], m["od"]
    return Cell(
        t=int(BY_PREFIX.get(m["t"], Terrain.GRASS)),
        view=int(m["view"]),
        m=_mir_code(m["mir"]),
        rt=_RIVER_REV.get(river, 0),
        rd=int(rd) if rd is not None else 0,
        ot=_ROAD_REV.get(road, 0),
        od=int(od) if od is not None else 0,
    )

"""Tile art: which picture each tile of a terrain grid shows.

A `Cell` is one tile as VCMI draws it: the terrain, the frame (`view`), the mirror flag
(`m`) and any river or road with its own frame and flip. `tile` gives each tile of a
`Terrain` grid the frame and flip the corpus maps use for the same terrain with the same
eight neighbours, so shores, beaches and land-land blends come out as the editor draws them.
It backs off from the exact eight neighbours to the four orthogonal ones, then to a clean
interior frame. A road tile gets the road frame and flip the corpus uses for the same
pattern of road neighbours, backing off the same way. Tiling draws no random number, so the
exported map and the PNG render show the same art.

A tile string is VCMI's: the terrain prefix, frame and flip, then the road's code, frame and
flip, then the river's. The codes are the ``shortIdentifier`` values of VCMI's
``config/roads.json`` and ``config/rivers.json``.

`THIN_DRAWABLE` names the terrains whose tilesets can draw a shape one tile wide. Terrain
generation passes it to despeckle, which erodes one-wide shapes of every other terrain.
"""

from __future__ import annotations

import collections
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.model.road import Road
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.vcmi.terrain import BY_PREFIX, prefix_of

type ViewMirror = tuple[int, int]
type SigTable = dict[tuple[int, tuple[int, ...]], collections.Counter[ViewMirror]]
type MaskTable = dict[int, collections.Counter[ViewMirror]]

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

RIVER = {1: "rw", 2: "ri", 3: "rm", 4: "rl"}
_RIVER_REV = {v: k for k, v in RIVER.items()}
ROAD: dict[Road, str] = {Road.DIRT: "pd", Road.GRAVEL: "pg", Road.COBBLESTONE: "pc"}
_ROAD_REV = {v: k for k, v in ROAD.items()}

_TILE_RE = re.compile(
    r"^(?P<t>[a-z]{2})(?P<view>\d+)(?P<mir>[+|_-])"
    + r"(?:(?P<road>pd|pg|pc)(?P<od>\d+)(?P<om>[+|_-]))?"
    + r"(?:(?P<river>rw|ri|rm|rl)(?P<rd>\d+)(?P<rm>[+|_-]))?$"
)

_NO_ROADS: Mapping[Tile, Road] = MappingProxyType({})

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
    rm: int = 0
    om: int = 0


@dataclass(frozen=True, slots=True)
class TilerTables:
    """The frames the corpus uses, counted per tile: ``exact`` keyed by terrain and the eight
    neighbour terrains, ``four`` keyed by terrain and the N, W, E, S neighbours, and
    ``clean`` keyed by terrain for tiles whose eight neighbours all share it. The road frames
    are counted per road tile: ``road_exact`` keyed by the ``road_mask`` of its eight
    neighbours and ``road_four`` keyed by the mask of its N, W, E, S neighbours alone."""

    exact: SigTable
    four: SigTable
    clean: dict[int, collections.Counter[ViewMirror]]
    road_exact: MaskTable = field(default_factory=dict[int, collections.Counter[ViewMirror]])
    road_four: MaskTable = field(default_factory=dict[int, collections.Counter[ViewMirror]])


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


def road_mask(roads: Mapping[Tile, int], x: int, y: int) -> int:
    """One bit per neighbour of ``(x, y)`` in the order of ``neighbours8``, set when that
    neighbour carries a road of any type."""
    return sum(1 << i for i, (dx, dy) in enumerate(_N8) if (x + dx, y + dy) in roads)


ROAD_FOUR_BITS = 0b01011010


VARIANT_SHARE = 0.25
"""A road frame counts as a variant of its pattern's most common frame when the corpus draws
it at least this share as often. The corpus alternates such variants, for example the two
straight frames, so the tiler picks one by position."""


def _road_frame(mask: int, x: int, y: int, tables: TilerTables) -> ViewMirror:
    hit = tables.road_exact.get(mask) or tables.road_four.get(mask & ROAD_FOUR_BITS)
    if not hit:
        return (0, 0)
    ranked = hit.most_common()
    opts = sorted(vm for vm, n in ranked if n >= VARIANT_SHARE * ranked[0][1])
    return opts[(x * 7 + y * 13) % len(opts)]


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


def tile(
    terrain: Sequence[Sequence[Terrain]],
    tables: TilerTables,
    roads: Mapping[Tile, Road] = _NO_ROADS,
) -> list[list[Cell]]:
    """Each tile of ``terrain`` with the frame and flip the corpus uses for it, and the road
    of ``roads`` with its frame and flip where a tile carries one."""
    grid = [[int(t) for t in row] for row in terrain]
    cells = [
        [_tile_cell(t, neighbours8(grid, x, y), x, y, tables) for x, t in enumerate(row)]
        for y, row in enumerate(grid)
    ]
    for (x, y), road in sorted(roads.items()):
        od, om = _road_frame(road_mask(roads, x, y), x, y, tables)
        c = cells[y][x]
        cells[y][x] = Cell(c.t, c.view, c.m, ot=int(road), od=od, om=om)
    return cells


def _mir(m: int) -> str:
    h, v = m & 1, m & 2
    return "+" if (h and v) else "|" if v else "-" if h else "_"


def _mir_code(ch: str) -> int:
    return {"+": 3, "|": 2, "-": 1, "_": 0}[ch]


def tile_string(c: Cell) -> str:
    s = f"{prefix_of(c.t)}{c.view}{_mir(c.m)}"
    if c.ot:
        s += f"{ROAD[Road(c.ot)]}{c.od}{_mir(c.om)}"
    if c.rt:
        s += f"{RIVER[c.rt]}{c.rd}{_mir(c.rm)}"
    return s


def tile_strings(
    terrain: Sequence[Sequence[Terrain]],
    tables: TilerTables,
    roads: Mapping[Tile, Road] = _NO_ROADS,
) -> list[list[str]]:
    return [[tile_string(c) for c in row] for row in tile(terrain, tables, roads)]


def decode_tile_string(s: str) -> Cell:
    """Inverse of `tile_string`: a VCMI tile token to its `Cell`."""
    m = _TILE_RE.match(s)
    if not m:
        raise ValueError(f"not a VCMI tile string: {s!r}")
    road, river = m["road"], m["river"]
    return Cell(
        t=int(BY_PREFIX.get(m["t"], Terrain.GRASS)),
        view=int(m["view"]),
        m=_mir_code(m["mir"]),
        rt=_RIVER_REV.get(river, 0),
        rd=int(m["rd"]) if river else 0,
        ot=int(_ROAD_REV[road]) if road else 0,
        od=int(m["od"]) if road else 0,
        rm=_mir_code(m["rm"]) if river else 0,
        om=_mir_code(m["om"]) if road else 0,
    )

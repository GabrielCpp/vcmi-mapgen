"""Corpus-match report: where gameplay objects sit in corpus zones and in generated zones.

For every counted object type it compares four measures of the entrance tile: depth from
the zone edge, walking distance to the nearest zone gate, openness of the 5x5 window around
the entrance with vegetation drawn, and back contact of the sprite top. It then compares
the number of counted objects per zone, bucketed by zone size.

    uv run python -m vcmi_mapgen.cli corpus-match --seeds 1 2 3 --size 48 --subterrain
"""

import collections
import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import final

from vcmi_mapgen.core.grid.geometry import edge_dist
from vcmi_mapgen.core.grid.segment import ZoneLabel, segment_level
from vcmi_mapgen.core.model import Cell, Identity, MapState, PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import COUNTED
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.placement.intensity import gate_dist
from vcmi_mapgen.core.placement.site import back_score
from vcmi_mapgen.core.planning.entrances import zone_fronts, zone_gates
from vcmi_mapgen.corpus.maps import all_map_names, load_corpus_map

MEASURES = ("depth", "gate", "open", "back")
EDGES = (20, 60, 100, 150, 250, 500, 1000)
VEGETATION = ("", "DECORATION")


@final
@dataclass(slots=True)
class Tally:
    measures: collections.defaultdict[tuple[str, str], list[int]] = field(
        default_factory=lambda: collections.defaultdict(list)
    )
    zones: collections.defaultdict[int, list[int]] = field(
        default_factory=lambda: collections.defaultdict(list)
    )


@dataclass(frozen=True, slots=True)
class _Field:
    unwalkable: set[Tile]
    veg: set[Tile]
    size: tuple[int, int]


def _entrance(o: PlacedObject) -> Tile:
    vis = FP.interactive_cells(o.footprint, o.x, o.y)
    return vis[0] if vis else (o.x, o.y)


def _field(grid: Sequence[Sequence[Cell]], objs: Sequence[PlacedObject]) -> _Field:
    unwalkable = {
        (x, y) for y, row in enumerate(grid) for x, c in enumerate(row) if Terrain(c.t).is_barrier
    }
    veg: set[Tile] = set()
    for o in objs:
        blk = [t for t, role in o.footprint.at(o.x, o.y) if role.blocks]
        unwalkable.update(blk)
        if o.purpose in VEGETATION:
            veg.update(blk)
    return _Field(unwalkable, veg, (len(grid[0]) if grid else 0, len(grid)))


def _back(o: PlacedObject, fld: _Field) -> int:
    own = {t for t, _role in o.footprint.at(o.x, o.y)} & fld.unwalkable
    fld.unwalkable.difference_update(own)
    score = back_score(
        Identity(o.type, o.subtype, o.animation, o.footprint), (o.x, o.y), fld.unwalkable, fld.size
    )
    fld.unwalkable.update(own)
    return score


def _window(e: Tile, open_tiles: set[Tile]) -> int:
    return sum(
        1 for dx in range(-2, 3) for dy in range(-2, 3) if (e[0] + dx, e[1] + dy) in open_tiles
    )


def _zone_gate_dist(ts: set[Tile], zone_label: ZoneLabel, zid: int) -> dict[Tile, int]:
    fronts = [t for front in zone_fronts(ts, zone_label, zid).values() for t in front]
    return gate_dist(ts, fronts or zone_gates(ts, zone_label, zid))


def _measure_zone(
    tally: Tally, fld: _Field, ts: set[Tile], gd: Mapping[Tile, int], objs: Sequence[PlacedObject]
) -> None:
    ed = edge_dist(ts)
    open_tiles = ts - fld.veg
    for o in objs:
        e = _entrance(o)
        row = {
            "depth": ed.get(e),
            "gate": gd.get(e),
            "open": _window(e, open_tiles),
            "back": _back(o, fld),
        }
        for k, v in row.items():
            if v is not None:
                tally.measures[(o.purpose, k)].append(v)


def measure_level(
    tally: Tally, grid: Sequence[Sequence[Cell]], objs: Sequence[PlacedObject]
) -> None:
    zones, label, _ = segment_level([list(row) for row in grid])
    fld = _field(grid, objs)
    w, h = fld.size
    by_zone: collections.defaultdict[int, list[PlacedObject]] = collections.defaultdict(list)
    for o in objs:
        x, y = _entrance(o)
        if o.purpose in COUNTED and 0 <= x < w and 0 <= y < h and label[y][x] >= 0:
            by_zone[label[y][x]].append(o)
    for zid, z in zones.items():
        if z.area < EDGES[0]:
            continue
        tally.zones[z.area].append(len(by_zone[zid]))
        if by_zone[zid]:
            ts = set(z.tiles_set)
            _measure_zone(tally, fld, ts, _zone_gate_dist(ts, label, zid), by_zone[zid])


def corpus_tally() -> Tally:
    tally = Tally()
    for name in all_map_names():
        m = load_corpus_map(name)
        for level, grid in m.cells.items():
            measure_level(tally, grid, [o for o in m.objs if o.level == level])
    return tally


def generated_tally(states: Iterable[MapState]) -> Tally:
    tally = Tally()
    for state in states:
        for level, grid in state.cells.items():
            measure_level(tally, grid, [o for o in state.objs if o.level == level])
    return tally


def _mean(xs: Sequence[int]) -> str:
    return f"{statistics.fmean(xs):5.1f}" if xs else "    -"


def _pct(xs: Sequence[int], q: int) -> int:
    s = sorted(xs)
    return s[min(len(s) - 1, len(s) * q // 10)]


def measure_report(corpus: Tally, gen: Tally) -> list[str]:
    head = f"{'type':16} {'n corp':>6} {'n gen':>6}" + "".join(
        f" {m + ' c':>7} {m + ' g':>7}" for m in MEASURES
    )
    lines = [head]
    for purpose in COUNTED:
        nc, ng = len(corpus.measures[(purpose, "open")]), len(gen.measures[(purpose, "open")])
        if not nc and not ng:
            continue
        cells = "".join(
            f"   {_mean(corpus.measures[(purpose, m)])}   {_mean(gen.measures[(purpose, m)])}"
            for m in MEASURES
        )
        lines.append(f"{purpose:16} {nc:6} {ng:6}{cells}")
    return lines


def _bucket(tally: Tally, lo: int, hi: int) -> tuple[list[int], int]:
    counts = [n for area, ns in tally.zones.items() if lo <= area < hi for n in ns]
    tiles = sum(area * len(ns) for area, ns in tally.zones.items() if lo <= area < hi)
    return counts, tiles


def bucket_report(corpus: Tally, gen: Tally) -> list[str]:
    lines = [
        f"{'zone tiles':>10} {'corpus p10/p50/p90':>19} {'rate':>5}  "
        + f"{'gen':>12} {'rate':>5} {'in band':>8}"
    ]
    for lo, hi in zip(EDGES, (*EDGES[1:], 10**9), strict=True):
        cc, ct = _bucket(corpus, lo, hi)
        gc, gt = _bucket(gen, lo, hi)
        if not cc:
            continue
        p10, p50, p90 = _pct(cc, 1), _pct(cc, 5), _pct(cc, 9)
        inside = sum(1 for n in gc if p10 <= n <= p90)
        gen_band = f"{_pct(gc, 1)}/{_pct(gc, 5)}/{_pct(gc, 9)}" if gc else "-"
        lines.append(
            f"{lo:>4}-{hi if hi < 10**9 else '':<5} {f'{p10}/{p50}/{p90}':>19} "
            + f"{100 * sum(cc) / ct:5.2f}  {gen_band:>12} "
            + f"{100 * sum(gc) / gt if gt else 0:5.2f} {f'{inside}/{len(gc)}':>8}"
        )
    return lines

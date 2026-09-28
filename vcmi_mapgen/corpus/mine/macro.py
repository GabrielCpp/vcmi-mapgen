"""Mine the macro terrain statistics: zone areas, terrain shares, terrain adjacency and
barrier fraction per level."""

import collections
from collections.abc import Iterable

from vcmi_mapgen.core.grid.segment import segment_level
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.priors.macro import MacroStats


def _mine_zones(
    lvl: list[list[Terrain]], areas: list[int], terr_share: collections.Counter[int]
) -> int:
    zones, _, _ = segment_level(lvl)
    big = 0
    for z in zones.values():
        t = z.terrain_type
        if t.is_land:
            areas.append(z.area)
            terr_share[t] += z.area
            if z.area >= 60:
                big += 1
    return big


def _mine_adjacency(T: list[list[int]], W: int, H: int, adj: collections.Counter[str]) -> None:
    for y in range(H):
        for x in range(W):
            a = T[y][x]
            for dx, dy in ((1, 0), (0, 1)):
                if x + dx < W and y + dy < H:
                    b = T[y + dy][x + dx]
                    if a != b and Terrain(a).is_land and Terrain(b).is_land:
                        adj[f"{min(a, b)}|{max(a, b)}"] += 1


def mine_macro(level: int, maps: Iterable[MapState]) -> MacroStats:
    """Corpus macro stats for terrain level `level` (0 = surface, 1 = underground). The
    underground table is mined independently from `fm["terrain"][1]` of two-level corpus
    maps — real underground zone areas/adjacency/barrier fraction are statistically distinct
    from the surface (rock, not subterr, is the dominant barrier terrain there; see corpus
    histograms in the design notes), so it is never derived from or blended with level-0 stats."""
    barrier = Terrain.WATER if level == 0 else Terrain.ROCK
    areas: list[int] = []
    barrier_fracs: list[float] = []
    terr_share = collections.Counter[int]()
    adj = collections.Counter[str]()  # "t1|t2" boundary-tile counts, t1 <= t2
    nzones: list[int] = []
    for fm in maps:
        if level >= len(fm.terrain):
            continue
        lvl = fm.terrain[level]
        H = len(lvl)
        W = len(lvl[0]) if H else 0
        T = [[int(t) for t in row] for row in lvl]
        nb = sum(1 for row in T for t in row if t == barrier)
        barrier_fracs.append(nb / max(W * H, 1))
        nzones.append(_mine_zones(lvl, areas, terr_share))
        _mine_adjacency(T, W, H, adj)
    st = MacroStats(
        areas=sorted(areas),
        barrier_fracs=sorted(barrier_fracs),
        terr_share=dict(terr_share),
        adj=dict(adj),
        nzones=nzones,
    )
    return st

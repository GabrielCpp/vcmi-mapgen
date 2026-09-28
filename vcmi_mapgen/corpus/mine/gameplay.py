"""Mine the per-terrain gameplay statistics from the corpus maps: the densities, sprite
weights and placement covariates the gameplay step draws from, cached in
``data/pp/gameplay_stats.json``."""

import collections
from collections.abc import Iterable
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.geometry import edge_dist
from vcmi_mapgen.core.grid.segment import ZoneLabel, segment_level
from vcmi_mapgen.core.model import MapState, PlacedObject, Tile, Zone
from vcmi_mapgen.core.model.purpose import PICKUP_PURPOSES, VISIT_PURPOSES, Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.placement.intensity import (
    EB,
    GB,
    OB,
    Covariates,
    gate_bin,
    gate_dist,
    open_bin,
    openness,
)
from vcmi_mapgen.core.planning.entrances import zone_fronts, zone_gates
from vcmi_mapgen.core.priors.gameplay import TerrainStats
from vcmi_mapgen.corpus.mine.gates import MIN_AREA_STATS

ALL_PURPOSES = (
    Purpose.TOWN,
    Purpose.MINE,
    Purpose.DWELLING,
    Purpose.WATER_TRANSPORT,
    Purpose.TRANSPORT,
    Purpose.BANK,
    *VISIT_PURPOSES,
    *PICKUP_PURPOSES,
)


@dataclass(slots=True)
class _TerrainAcc:
    tiles: int = 0
    counts: collections.Counter[str] = field(default_factory=collections.Counter)
    anim_w: collections.defaultdict[str, collections.Counter[str]] = field(
        default_factory=lambda: collections.defaultdict(collections.Counter)
    )
    e: collections.defaultdict[str, list[int]] = field(
        default_factory=lambda: collections.defaultdict(lambda: [0] * EB)
    )
    g: collections.defaultdict[str, list[int]] = field(
        default_factory=lambda: collections.defaultdict(lambda: [0] * GB)
    )
    o: collections.defaultdict[str, list[int]] = field(
        default_factory=lambda: collections.defaultdict(lambda: [0] * OB)
    )
    tiles_e: list[int] = field(default_factory=lambda: [0] * EB)
    tiles_g: list[int] = field(default_factory=lambda: [0] * GB)
    tiles_o: list[int] = field(default_factory=lambda: [0] * OB)
    guarded: collections.Counter[str] = field(default_factory=collections.Counter)
    guardable: collections.Counter[str] = field(default_factory=collections.Counter)
    border_tiles: int = 0
    border_open: int = 0


@dataclass(frozen=True, slots=True)
class _CorpusLevel:
    catalog: Catalog
    fm: MapState
    level: int
    zone_label: ZoneLabel
    guards: AbstractSet[Tile]


def _accumulate_water(aw: _TerrainAcc, fm: MapState, level: int) -> None:
    wtiles = {
        (x, y)
        for y, row in enumerate(fm.terrain[level])
        for x, t in enumerate(row)
        if t == Terrain.WATER
    }
    if not wtiles:
        return
    aw.tiles += len(wtiles)
    for o in fm.objs:
        if o.level != level or (o.x, o.y) not in wtiles:
            continue
        p = Purpose(o.purpose)
        if p in ALL_PURPOSES:
            aw.counts[p] += 1
            anim = o.kind.lower().removesuffix(".def")
            if anim:
                aw.anim_w[p][anim] += 1


def _zone_blocked(
    catalog: Catalog, zone_objs: Iterable[PlacedObject], ts: AbstractSet[Tile]
) -> tuple[set[Tile], set[Tile]]:
    veg_blocked: set[Tile] = set()
    all_blocked: set[Tile] = set()
    for o in zone_objs:
        is_decor = o.purpose == Purpose.DECORATION
        anim = o.kind.lower().removesuffix(".def")
        for cx, cy, blk in FP.anchored_cells(catalog.identity_of(anim).footprint, o.x, o.y):
            if blk and (cx, cy) in ts:
                all_blocked.add((cx, cy))
                if is_decor:
                    veg_blocked.add((cx, cy))
    return veg_blocked, all_blocked


def _count_zone_obj(
    a: _TerrainAcc, o: PlacedObject, cov: Covariates, guards: AbstractSet[Tile]
) -> None:
    p = Purpose(o.purpose)
    if p not in ALL_PURPOSES:
        return
    t = (o.x, o.y)
    a.counts[p] += 1
    anim = o.kind.lower().removesuffix(".def")
    if anim:
        a.anim_w[p][anim] += 1
    a.e[p][min(cov.ed[t], EB - 1)] += 1
    a.g[p][gate_bin(cov.gd.get(t, 12))] += 1
    op = cov.op
    if op is not None and t in op:
        a.o[p][open_bin(op[t])] += 1
    if p in (Purpose.RESOURCE_PILE, Purpose.REWARD_PICKUP, Purpose.MINE):
        a.guardable[p] += 1
        if any(max(abs(t[0] - gx), abs(t[1] - gy)) <= 3 for gx, gy in guards):
            a.guarded[p] += 1


def _accumulate_zone(a: _TerrainAcc, cl: _CorpusLevel, zid: int, z: Zone) -> None:
    ts = set(z.tiles_set)
    a.tiles += len(ts)
    ed = edge_dist(ts)
    fronts = zone_fronts(ts, cl.zone_label, zid)
    front_union = set[Tile]().union(*fronts.values()) if fronts else set[Tile]()
    gd = gate_dist(ts, front_union or zone_gates(ts, cl.zone_label, zid))
    zone_objs = [o for o in cl.fm.objs if o.level == cl.level and (o.x, o.y) in ts]
    veg_blocked, all_blocked = _zone_blocked(cl.catalog, zone_objs, ts)
    a.border_tiles += len(front_union)
    a.border_open += sum(1 for t in front_union if t not in all_blocked)
    op = openness(ts - veg_blocked)
    for t in ts:
        a.tiles_e[min(ed[t], EB - 1)] += 1
        a.tiles_g[gate_bin(gd.get(t, 12))] += 1
        if t in op:
            a.tiles_o[open_bin(op[t])] += 1
    cov = Covariates(ed, gd, op)
    for o in zone_objs:
        _count_zone_obj(a, o, cov, cl.guards)


def _accumulate_map(
    catalog: Catalog, acc: dict[str, _TerrainAcc], fm: MapState, level: int
) -> None:
    zones, zone_label, _ = segment_level(fm.terrain[level])
    guards = {(o.x, o.y) for o in fm.objs if o.level == level and o.purpose == Purpose.GUARD}
    _accumulate_water(acc["water"], fm, level)
    cl = _CorpusLevel(catalog, fm, level, zone_label, guards)
    for zid, z in zones.items():
        terr = catalog.terrain_name(z.terrain_type)
        if terr not in acc or z.area < MIN_AREA_STATS:
            continue
        _accumulate_zone(acc[terr], cl, zid, z)


def _finish_stats(a: _TerrainAcc) -> TerrainStats:
    return TerrainStats(
        tiles=a.tiles,
        counts=dict(a.counts),
        anim_w={p: dict(c) for p, c in a.anim_w.items()},
        e=dict(a.e),
        g=dict(a.g),
        o=dict(a.o),
        tiles_e=a.tiles_e,
        tiles_g=a.tiles_g,
        tiles_o=a.tiles_o,
        border_open_frac=(a.border_open / a.border_tiles if a.border_tiles else 0.5),
        guard_frac={
            p: (a.guarded[p] / a.guardable[p] if a.guardable[p] else 0.0)
            for p in (Purpose.RESOURCE_PILE, Purpose.REWARD_PICKUP, Purpose.MINE)
        },
    )


def land_names(catalog: Catalog) -> tuple[str, ...]:
    """The stats keys of the land terrains, in `Terrain` order."""
    return tuple(catalog.terrain_name(t) for t in Terrain if t.is_land)


def mine_gameplay(
    catalog: Catalog, level: int, maps: Iterable[MapState]
) -> dict[str, TerrainStats]:
    """Corpus statistics for the FULL L3 intensity fit, per terrain, for terrain level `level`
    (0 = surface, 1 = underground):

    - per-purpose counts + animation frequencies (density and mix),
    - per-purpose covariate histograms — counts by edge-dist bin, gate-dist bin, and (for
      pickups) OPENNESS bin of the veg-only open field — the sufficient statistics of the
      log-linear intensity  lam_p(u) ∝ exp(th_e[e(u)] + th_g[g(u)] + th_o[o(u)]),
    - tiles per covariate bin (the exposure normalizers),
    - guardedness: fraction of resource piles / pickups / MINES with a GUARD within
      Chebyshev 3,
    - a "water" entry: purpose densities inside water zones (flotsam, buoys, boats,
      shipwrecks, whirlpools, sea guards) — water can appear on either level.

    The underground table (`level=1`) is mined independently from two-level corpus maps'
    `fm["terrain"][1]`, exactly mirroring the surface mining below — never derived from or
    blended with the level-0 table (real underground object density is statistically
    distinct: smaller, sparser zones), matching `corpus.mine.macro.mine_macro`'s precedent.
    """
    acc = {t: _TerrainAcc() for t in (*land_names(catalog), "water")}
    for fm in maps:
        if level >= len(fm.terrain):
            continue
        _accumulate_map(catalog, acc, fm, level)
    return {t: _finish_stats(a) for t, a in acc.items()}

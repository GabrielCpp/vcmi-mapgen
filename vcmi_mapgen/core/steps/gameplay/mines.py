"""Gameplay corpus statistics: the per-terrain densities, sprite weights and placement
covariates the gameplay step draws from, plus the shared economy helpers.

  - **counts** come from corpus per-purpose densities (objects per zone tile, mined per
    terrain and cached in ``data/pp/gameplay_stats.json``),
  - **identities** come from the catalog's `gameplay_pool` (never the corpus); a zone with
    >= 2 mines is guaranteed a sawmill + ore pit first (the H3 economy convention),
  - **placement intensity** is the fitted per-tile weight over edge depth, gate distance
    and openness (`intensity_weights`).

`steps.gameplay.draw` turns these into one zone's identities and `steps.gameplay.site`
places them after vegetation.
"""

import collections
from collections.abc import Callable, Iterable, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.geometry import edge_dist
from vcmi_mapgen.core.grid.segment import ZoneLabel, segment_level
from vcmi_mapgen.core.model import Identity, MapState, PlacedObject, Tile, Zone
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
from vcmi_mapgen.corpus.gameplay import (
    load_gameplay,
)
from vcmi_mapgen.corpus.mine.gates import MIN_AREA_STATS

TOWN_MIN_AREA = 150  # a town needs a real zone
WATER_PURPOSES = (
    Purpose.REWARD_PICKUP,
    Purpose.BONUS_TEMP,
    Purpose.TRANSPORT,
    Purpose.INFO,
    Purpose.BANK,
    Purpose.WATER_TRANSPORT,
    # no guard -- a monster only ever gates a mine, a loot-zone/portal-rescue access
    # object, or a pocket mouth (user-mandated placement order); water bodies get none.
)
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
# soft caps only guard against pathological zones — corpus densities set the real counts.
# They are BASE floors: the effective cap scales with zone area (`scaled_cap`), so a
# 5000-tile zone is not clamped to the same handful of objects as a 600-tile one.
# the six basic resource mines every map must cover (gold is the deliberate exception:
# only worth placing when the map holds several towns)
BASIC_MINE_RES = ("sawmill", "orePit", "alchemistLab", "sulfurDune", "crystalCavern", "gemPond")

# The H3 mapmaking convention (user-mandated): most placed objects are the editor's RANDOM
# classes — random town/dwelling/monster/resource/artifact — with a few fixed ones. All of
# these have real sprites (checked via catalog.spec).
RND_TOWN = "avcranx0"  # randomTown
RND_DWELL = "avrcgen0"  # randomDwelling (any level)
RND_DWELL_L = tuple(f"avrcgen{i}" for i in range(1, 8))  # randomDwellingLvl 1..7
RANDOM_SHARE = 0.7  # towns: random vs fixed split


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
class AuditGap:
    purpose: str
    anim: str
    count: int
    why: str


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
        for y, row in enumerate(fm.cells[level])
        for x, c in enumerate(row)
        if c.t == Terrain.WATER
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
            anim = o.animation.lower().removesuffix(".def")
            if anim:
                aw.anim_w[p][anim] += 1


def _zone_blocked(
    catalog: Catalog, zone_objs: Iterable[PlacedObject], ts: AbstractSet[Tile]
) -> tuple[set[Tile], set[Tile]]:
    veg_blocked: set[Tile] = set()
    all_blocked: set[Tile] = set()
    for o in zone_objs:
        is_decor = o.purpose == Purpose.DECORATION
        anim = o.animation.lower().removesuffix(".def")
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
    anim = o.animation.lower().removesuffix(".def")
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
    zones, zone_label, _ = segment_level(fm.cells[level])
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
    distinct: smaller, sparser zones), matching `macro_topo.mine_macro`'s precedent.
    """
    acc = {t: _TerrainAcc() for t in (*land_names(catalog), "water")}
    for fm in maps:
        if level >= len(fm.cells):
            continue
        _accumulate_map(catalog, acc, fm, level)
    return {t: _finish_stats(a) for t, a in acc.items()}


def info_pool(
    catalog: Catalog, terrain: str, has_water: bool, has_subterrain: bool = False
) -> list[Identity]:
    """`catalog.candidates(Purpose.INFO, terrain)`, minus cartographer subtypes the map
    can't back up:
    cartographerSubterranean is dropped unless the map actually has a second level, and
    cartographerWater is dropped on maps with no water at all."""
    pool = catalog.candidates(Purpose.INFO, terrain)
    return [
        i
        for i in pool
        if (i.subtype != "cartographerSubterranean" or has_subterrain)
        and (i.subtype != "cartographerWater" or has_water)
    ]


@dataclass(slots=True)
class Ledger:
    missing: set[str]
    towns: int
    gold: int


def mine_variants(ids: list[Identity], mine_w: Mapping[str, int]) -> list[Identity]:
    """Terrain-faithful sprite variants: mine DEFs carry a baked-in terrain apron
    (avmgogr0 grass vs avmgold0 dirt), so keep only the variants mapmakers actually
    use on THIS terrain (>= 20% of the top variant's corpus weight — drops the rare
    cross-terrain leakage that put dirt-apron mines on grass)."""
    ws = {i.animation.lower(): mine_w.get(i.animation.lower(), 0) for i in ids}
    top = max(ws.values(), default=0)
    if top > 0:
        keep = [i for i in ids if ws[i.animation.lower()] >= 0.2 * top]
        return keep or ids
    return ids


def rest_mines(
    mines: Mapping[str, list[Identity]], used_res: AbstractSet[str], ledger: Ledger | None
) -> dict[str, list[Identity]]:
    gold_ok = ledger is None or ledger.gold < max(0, ledger.towns - 1)
    return {
        res: ids
        for res, ids in mines.items()
        if res not in used_res
        and ids
        and res not in ("abandoned", "mine")  # both abandoned-mine variants
        and (res != "goldMine" or gold_ok)
    }


def tie_dwellings(objs: Iterable[PlacedObject]) -> None:
    # tie the zone's RANDOM dwellings to its town: VCMI's `sameAsTown` link makes the
    # dwelling resolve to the town's (lobby-picked) faction at game start, so the creatures
    # around a random town are its own. Instance names are minted only at export, so the
    # marker carries the town's coordinates; `renderers.vmap.VmapRenderer._build_document`
    # swaps in the instanceName.
    town = next((o for o in objs if o.purpose == Purpose.TOWN), None)
    if town is not None:
        for o in objs:
            if (o.type or "").startswith("randomDwelling"):
                if o.options is None:
                    o.options = {}
                o.options["sameAsTown"] = [town.x, town.y, town.level]


# purposes deliberately NOT reproduced by the generator (the audit's whitelist)
AUDIT_EXCLUDED = {
    Purpose.TRANSPORT: "relational: subterranean gates + two-way monoliths are placed by their own "
    + "matched-set passes (place_gate_pairs / PortalStep), not the "
    + "per-zone density draw — the audit must not demand every corpus variant",
    Purpose.GUARD: "guards are leveled RANDOM monsters by design, never corpus identities",
}
# corpus sprite VARIANTS of catalog objects: same {type, subtype} gameplay object under a
# different DEF filename (fort-less 'village' town sprites vs the editor's forted '..x0'
# sprite; the corpus's "AVGnoll" gnoll-hut DEF vs the editor table's "avggnll0") — the audit
# treats them as reachable through their canonical animation.
TOWN_SPRITE_VARIANTS = {
    "avcrand0": "avcranx0",
    "avccast0": "avccasx0",
    "avcramp0": "avcramx0",
    "avctowr0": "avctowx0",
    "avcinft0": "avcinfx0",
    "avcnecr0": "avcnecx0",
    "avcdung0": "avcdunx0",
    "avcstro0": "avcstrx0",
    "avcftrt0": "avcftrx0",
    "avchfor0": "avchforx",
    "avgnoll": "avggnll0",
}
# purposes the generator actually places on land (BANK included since the land-bank change)
PLACED_PURPOSES = (
    set(VISIT_PURPOSES)
    | set(PICKUP_PURPOSES)
    | {Purpose.TOWN, Purpose.MINE, Purpose.DWELLING, Purpose.BANK, Purpose.WATER_TRANSPORT}
) - set(AUDIT_EXCLUDED)


def audit_variety(catalog: Catalog, level: int = 0) -> list[AuditGap]:
    """Corpus-variety audit: every (purpose, animation) with a nonzero corpus count on land
    must (a) resolve through the catalog and (b) be reachable through a generator pool —
    i.e. its purpose is placed and the animation sits in `gameplay_pool` for at least one
    land terrain (or it is an editor RANDOM class, placed by convention). Returns a list of
    `AuditGap`s (empty = the generated maps can reach the corpus's full visitable variety).
    `level` selects which level's corpus stats table to audit (0 = surface, 1 = underground:
    both must stay green since `--subterrain` places gameplay from the level-1 table too)."""
    st = load_gameplay(level=level)
    land = land_names(catalog)
    seen: dict[tuple[str, str], int] = {}  # (purpose, anim) -> total corpus count
    for terr in land:
        for p, anims in st[terr].anim_w.items():
            if p in AUDIT_EXCLUDED:
                continue
            for anim, cnt in anims.items():
                seen[(p, anim)] = seen.get((p, anim), 0) + cnt
    pool_anims: dict[str, set[str]] = {}  # purpose -> anims reachable on ANY terrain incl water
    for p in {p for p, _a in seen}:
        pool_anims[p] = {
            i.animation.lower() for t in (*land, "water") for i in catalog.candidates(p, t)
        }
    gaps: list[AuditGap] = []
    for (p, raw_anim), cnt in sorted(seen.items(), key=lambda kv: (-kv[1], kv[0])):
        anim = TOWN_SPRITE_VARIANTS.get(raw_anim, raw_anim)
        ident = catalog.identity_of(anim)
        if catalog.spec(anim) is None:
            gaps.append(AuditGap(p, anim, cnt, "animation missing from the catalog"))
        elif p not in PLACED_PURPOSES:
            gaps.append(AuditGap(p, anim, cnt, f"purpose {p} not placed by the generator"))
        elif "random" not in (ident.type or "").lower() and anim not in pool_anims[p]:
            gaps.append(AuditGap(p, anim, cnt, "not in pool for any land terrain"))
    return gaps


def select_player_zones(
    zones_by_level: Mapping[int, Mapping[int, Zone]],
    players: int,
    can_host: Callable[[int, int], bool] = lambda _level, _zid: True,
) -> list[tuple[int, int]]:
    """Deterministic player-zone pick across BOTH terrain levels (surface always present;
    underground pooled in only when `--subterrain` is on): big land zones that are MUTUALLY
    FAR APART in (x, y) — the two levels share one coordinate system, so cross-level
    distance is compared the same way as same-level distance. Candidates are land zones
    >= 60 tiles, preferring real zones (>= 100 tiles and >= 1/4 of the largest, pooled across
    levels). The first pick is the largest zone overall; each next pick greedily maximizes
    the minimum centroid distance to the zones already chosen (tie-break: area desc, level,
    zid). A zone ``can_host`` refuses never becomes a candidate. Returns [(level, zid), ...]
    in player order."""
    cand = [
        (z.area, level, zid, z.centroid)
        for level, zones in zones_by_level.items()
        for zid, z in zones.items()
        if z.terrain_type.is_land and z.area >= 60 and can_host(level, zid)
    ]
    if not cand or players <= 0:
        return []
    cand.sort(key=lambda c: (-c[0], c[1], c[2]))
    amax = cand[0][0]
    pool = [c for c in cand if c[0] >= max(100, amax // 4)]
    if len(pool) < players:  # too few big zones: admit smaller ones
        pool = cand
    chosen = [pool[0]]
    rest = pool[1:]
    while len(chosen) < players and rest:
        best = max(
            rest,
            key=lambda c: (
                min((c[3][0] - ch[3][0]) ** 2 + (c[3][1] - ch[3][1]) ** 2 for ch in chosen),
                c[0],
                -c[1],
                -c[2],
            ),
        )
        chosen.append(best)
        rest.remove(best)
    return [(level, zid) for _a, level, zid, _c in chosen]

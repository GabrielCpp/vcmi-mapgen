"""Gameplay corpus statistics: the per-terrain densities, sprite weights and placement
covariates the gameplay step draws from, plus the shared economy helpers.

  - **counts** come from corpus per-purpose densities (objects per zone tile, mined per
    terrain and cached in ``data/pp/gameplay_stats.json``),
  - **identities** come from the ontology's `gameplay_pool` (never the corpus); a zone with
    >= 2 mines is guaranteed a sawmill + ore pit first (the H3 economy convention),
  - **placement intensity** is the fitted per-tile weight over edge depth, gate distance
    and openness (`intensity_weights`).

`steps.gameplay.draw` turns these into one zone's identities and `steps.gameplay.site`
places them after vegetation.
"""

import argparse
import collections
import math
from collections.abc import Callable, Iterable, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from pathlib import Path

from vcmi_mapgen.core.grid.geometry import edge_dist
from vcmi_mapgen.core.grid.segment import segment_level
from vcmi_mapgen.core.model import Identity, JsonValue, PlacedObject, Tile, Zone
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.steps.gate.gates import MIN_AREA_STATS
from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.kit import pp_cache
from vcmi_mapgen.kit.paths import project_root
from vcmi_mapgen.kit.topology import zone_fronts, zone_gates
from vcmi_mapgen.vcmi.catalog import decor as DC
from vcmi_mapgen.vcmi.catalog import objects as ON
from vcmi_mapgen.vcmi.formats import json_value as jv
from vcmi_mapgen.vcmi.terrain import LAND_NAMES, name_of

ROOT = project_root()
STATS_PATH = str(ROOT / "data" / "pp" / "gameplay_stats.json")
STATS_PATH_UNDERGROUND = str(ROOT / "data" / "pp" / "gameplay_stats_underground.json")
SOURCE = "vcmi_mapgen.core.steps.gameplay.mines.mine_gameplay"
STATS_VERSION = 5  # v5: border open fraction + full-front gate distances
TOWN_MIN_AREA = 150  # a town needs a real zone
VISIT_PURPOSES = ("STAT_PERMANENT", "SPELL_SKILL", "BONUS_TEMP", "MANA", "INFO")
PICKUP_PURPOSES = ("RESOURCE_PILE", "REWARD_PICKUP", "GUARD")
WATER_PURPOSES = (
    "REWARD_PICKUP",
    "BONUS_TEMP",
    "TRANSPORT",
    "INFO",
    "BANK",
    "WATER_TRANSPORT",
    # no "GUARD" -- a monster only ever gates a mine, a loot-zone/portal-rescue access
    # object, or a pocket mouth (user-mandated placement order); water bodies get none.
)
ALL_PURPOSES = (
    "TOWN",
    "MINE",
    "DWELLING",
    "WATER_TRANSPORT",
    "TRANSPORT",
    "BANK",
    *VISIT_PURPOSES,
    *PICKUP_PURPOSES,
)
# soft caps only guard against pathological zones — corpus densities set the real counts.
# They are BASE floors: the effective cap scales with zone area (`scaled_cap`), so a
# 5000-tile zone is not clamped to the same handful of objects as a 600-tile one.
# the six basic resource mines every map must cover (gold is the deliberate exception:
# only worth placing when the map holds several towns)
BASIC_MINE_RES = ("sawmill", "orePit", "alchemistLab", "sulfurDune", "crystalCavern", "gemPond")
# every base-game learnable spell (config/spells/{adventure,other,offensive,timed}.json,
# indices 0-69) — a town's Mage Guild picks its taught spells from this pool, so omitting
# it (as opposed to leaving it empty) is what VCMI reads as "no spells available". Creature
# abilities (config/spells/ability.json, indices 70-81: stoneGaze, poison, ...) are not
# learnable spells and are excluded, matching real VCMI RMG output.
CORE_SPELLS: list[JsonValue] = [
    "core:" + name
    for name in (
        "summonBoat",
        "scuttleBoat",
        "visions",
        "viewEarth",
        "disguise",
        "viewAir",
        "fly",
        "waterWalk",
        "dimensionDoor",
        "townPortal",
        "quicksand",
        "landMine",
        "forceField",
        "fireWall",
        "earthquake",
        "dispel",
        "cure",
        "resurrection",
        "animateDead",
        "sacrifice",
        "teleport",
        "removeObstacle",
        "clone",
        "fireElemental",
        "earthElemental",
        "waterElemental",
        "airElemental",
        "magicArrow",
        "iceBolt",
        "lightningBolt",
        "implosion",
        "chainLightning",
        "frostRing",
        "fireball",
        "inferno",
        "meteorShower",
        "deathRipple",
        "destroyUndead",
        "armageddon",
        "titanBolt",
        "shield",
        "airShield",
        "fireShield",
        "protectAir",
        "protectFire",
        "protectWater",
        "protectEarth",
        "antiMagic",
        "magicMirror",
        "bless",
        "curse",
        "bloodlust",
        "precision",
        "weakness",
        "stoneSkin",
        "disruptingRay",
        "prayer",
        "mirth",
        "sorrow",
        "fortune",
        "misfortune",
        "haste",
        "slow",
        "slayer",
        "frenzy",
        "counterstrike",
        "berserk",
        "hypnotize",
        "forgetfulness",
        "blind",
    )
]
LAND = LAND_NAMES
MINED_TERR = (*LAND, "water")
EB, GB, OB = 6, 4, 4  # covariate bins: edge-dist, gate-dist, openness

# The H3 mapmaking convention (user-mandated): most placed objects are the editor's RANDOM
# classes — random town/dwelling/monster/resource/artifact — with a few fixed ones. All of
# these have real sprites (checked via ontology.has_animation).
RND_TOWN = "avcranx0"  # randomTown
RND_DWELL = "avrcgen0"  # randomDwelling (any level)
RND_DWELL_L = tuple(f"avrcgen{i}" for i in range(1, 8))  # randomDwellingLvl 1..7
RND_RES = "avtrndm0"  # randomResource
RND_ART = (
    ("avarnd1", 50, 3),
    ("avarnd2", 30, 5),  # (anim, pick weight, reward value):
    ("avarnd3", 15, 8),
    ("avarand", 5, 5),
)  # treasure/minor/major/any artifact
RANDOM_SHARE = 0.7  # towns: random vs fixed split
# guard strength tracks the value guarded: mine guards by resource rarity. Every mine is
# guarded (user-reported bug: unguarded mines), valuable mines scaling higher still. The
# town's own economy pair (sawmill/orePit) is guarded at level 1 specifically (user-mandated
# — a trivial early fight, not a level-3+ wall in front of every town's starting economy).
MINE_GUARD_LVL = {
    "sawmill": 1,
    "orePit": 1,
    "waterWheel": 3,
    "windmill": 3,
    "mysticalGarden": 3,
    "alchemistLab": 4,
    "sulfurDune": 4,
    "gemPond": 5,
    "crystalCavern": 5,
    "goldMine": 6,
    "abandoned": 5,
}


def scaled_cap(base: int, expectation: float) -> int:
    """Area-scaled soft cap: the corpus expectation (density x area) drives the count; the
    cap only stops outliers (1.5x the expectation), never below the base floor."""
    return max(base, math.ceil(expectation * 1.5))


def _gbin(d: int) -> int:
    return min(d // 3, GB - 1)


def _obin(n_open_5x5: int) -> int:
    return min(n_open_5x5 // 7, OB - 1)


def gate_dist(ts: AbstractSet[Tile], gates: Iterable[Tile]) -> dict[Tile, int]:
    """4-connected BFS steps from the zone's rim gates (corpus + generated zones alike)."""
    d = {g: 0 for g in gates if g in ts}
    q = collections.deque(d)
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if n in ts and n not in d:
                d[n] = d[(x, y)] + 1
                q.append(n)
    return d


def openness(open_set: AbstractSet[Tile]) -> dict[Tile, int]:
    """Per open tile: number of open tiles in its 5x5 window (low = nook/chokepoint)."""
    out: dict[Tile, int] = {}
    for x, y in open_set:
        out[(x, y)] = sum(
            1 for dx in range(-2, 3) for dy in range(-2, 3) if (x + dx, y + dy) in open_set
        )
    return out


@dataclass(frozen=True, slots=True)
class TerrainStats:
    tiles: int
    counts: dict[str, int]
    anim_w: dict[str, dict[str, int]]
    e: dict[str, list[int]]
    g: dict[str, list[int]]
    o: dict[str, list[int]]
    tiles_e: list[int]
    tiles_g: list[int]
    tiles_o: list[int]
    border_open_frac: float
    guard_frac: dict[str, float]


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


def _number(value: JsonValue | None) -> float:
    return float(value) if isinstance(value, int | float) else 0.0


def _int_map(value: JsonValue | None) -> dict[str, int]:
    return {k: jv.as_int(v) for k, v in jv.as_object(value).items()}


def _int_list(value: JsonValue | None) -> list[int]:
    return [jv.as_int(v) for v in jv.as_list(value)]


def _int_lists(value: JsonValue | None) -> dict[str, list[int]]:
    return {k: _int_list(v) for k, v in jv.as_object(value).items()}


def _stats_from_json(value: JsonValue | None) -> TerrainStats:
    d = jv.as_object(value)
    return TerrainStats(
        tiles=jv.as_int(d.get("tiles")),
        counts=_int_map(d.get("counts")),
        anim_w={k: _int_map(v) for k, v in jv.as_object(d.get("anim_w")).items()},
        e=_int_lists(d.get("e")),
        g=_int_lists(d.get("g")),
        o=_int_lists(d.get("o")),
        tiles_e=_int_list(d.get("tiles_e")),
        tiles_g=_int_list(d.get("tiles_g")),
        tiles_o=_int_list(d.get("tiles_o")),
        border_open_frac=_number(d.get("border_open_frac")),
        guard_frac={k: _number(v) for k, v in jv.as_object(d.get("guard_frac")).items()},
    )


def _stats_to_json(st: TerrainStats) -> dict[str, JsonValue]:
    return {
        "tiles": st.tiles,
        "counts": {k: v for k, v in st.counts.items()},
        "anim_w": {p: {a: n for a, n in c.items()} for p, c in st.anim_w.items()},
        "e": {p: [n for n in v] for p, v in st.e.items()},
        "g": {p: [n for n in v] for p, v in st.g.items()},
        "o": {p: [n for n in v] for p, v in st.o.items()},
        "tiles_e": [n for n in st.tiles_e],
        "tiles_g": [n for n in st.tiles_g],
        "tiles_o": [n for n in st.tiles_o],
        "border_open_frac": st.border_open_frac,
        "guard_frac": {p: f for p, f in st.guard_frac.items()},
    }


def _stats_path(level: int) -> Path:
    return Path(STATS_PATH if level == 0 else STATS_PATH_UNDERGROUND)


def load_gameplay(level: int = 0) -> dict[str, TerrainStats]:
    st = pp_cache.read(_stats_path(level), version=STATS_VERSION)
    return {k: _stats_from_json(v) for k, v in st.items() if k not in pp_cache.META_KEYS}


def save_gameplay(level: int, stats: Mapping[str, TerrainStats]) -> None:
    payload: dict[str, object] = {"_version": STATS_VERSION}
    for t, tst in stats.items():
        payload[t] = _stats_to_json(tst)
    pp_cache.write(_stats_path(level), SOURCE, payload)


@dataclass(frozen=True, slots=True)
class Covariates:
    ed: Mapping[Tile, int]
    gd: Mapping[Tile, int]
    op: Mapping[Tile, int] | None = None


@dataclass(frozen=True, slots=True)
class _CorpusLevel:
    fm: OR.FaithfulMap
    level: int
    zones: Mapping[int, Zone]
    guards: AbstractSet[Tile]


def _accumulate_water(aw: _TerrainAcc, fm: OR.FaithfulMap, level: int) -> None:
    wtiles = {
        (x, y)
        for y, row in enumerate(fm.terrain[level])
        for x, c in enumerate(row)
        if c.t == Terrain.WATER
    }
    if not wtiles:
        return
    aw.tiles += len(wtiles)
    for o in fm.objects:
        if o.level != level or (o.x, o.y) not in wtiles:
            continue
        p = OR.purpose_of(o)
        if p in ALL_PURPOSES:
            aw.counts[p] += 1
            anim = o.animation.lower().removesuffix(".def")
            if anim:
                aw.anim_w[p][anim] += 1


def _zone_blocked(
    zone_objs: Iterable[PlacedObject], ts: AbstractSet[Tile]
) -> tuple[set[Tile], set[Tile]]:
    veg_blocked: set[Tile] = set()
    all_blocked: set[Tile] = set()
    for o in zone_objs:
        is_decor = OR.purpose_of(o) == "DECORATION"
        anim = o.animation.lower().removesuffix(".def")
        for cx, cy, blk in OR.mask_cells(ON.mask_of(anim), o.x, o.y):
            if blk and (cx, cy) in ts:
                all_blocked.add((cx, cy))
                if is_decor:
                    veg_blocked.add((cx, cy))
    return veg_blocked, all_blocked


def _count_zone_obj(
    a: _TerrainAcc, o: PlacedObject, cov: Covariates, guards: AbstractSet[Tile]
) -> None:
    p = OR.purpose_of(o)
    if p not in ALL_PURPOSES:
        return
    t = (o.x, o.y)
    a.counts[p] += 1
    anim = o.animation.lower().removesuffix(".def")
    if anim:
        a.anim_w[p][anim] += 1
    a.e[p][min(cov.ed[t], EB - 1)] += 1
    a.g[p][_gbin(cov.gd.get(t, 12))] += 1
    op = cov.op
    if op is not None and t in op:
        a.o[p][_obin(op[t])] += 1
    if p in ("RESOURCE_PILE", "REWARD_PICKUP", "MINE"):
        a.guardable[p] += 1
        if any(max(abs(t[0] - gx), abs(t[1] - gy)) <= 3 for gx, gy in guards):
            a.guarded[p] += 1


def _accumulate_zone(a: _TerrainAcc, cl: _CorpusLevel, zid: int, z: Zone) -> None:
    ts = set(z.tiles_set)
    a.tiles += len(ts)
    ed = edge_dist(ts)
    fronts = zone_fronts(ts, cl.zones, zid)
    front_union = set[Tile]().union(*fronts.values()) if fronts else set[Tile]()
    gd = gate_dist(ts, front_union or zone_gates(ts, cl.zones, zid))
    zone_objs = [o for o in cl.fm.objects if o.level == cl.level and (o.x, o.y) in ts]
    veg_blocked, all_blocked = _zone_blocked(zone_objs, ts)
    a.border_tiles += len(front_union)
    a.border_open += sum(1 for t in front_union if t not in all_blocked)
    op = openness(ts - veg_blocked)
    for t in ts:
        a.tiles_e[min(ed[t], EB - 1)] += 1
        a.tiles_g[_gbin(gd.get(t, 12))] += 1
        if t in op:
            a.tiles_o[_obin(op[t])] += 1
    cov = Covariates(ed, gd, op)
    for o in zone_objs:
        _count_zone_obj(a, o, cov, cl.guards)


def _accumulate_map(acc: dict[str, _TerrainAcc], fm: OR.FaithfulMap, level: int) -> None:
    zones, _zl, _ = segment_level(fm.terrain[level])
    guards = {(o.x, o.y) for o in fm.objects if o.level == level and OR.purpose_of(o) == "GUARD"}
    _accumulate_water(acc["water"], fm, level)
    cl = _CorpusLevel(fm, level, zones, guards)
    for zid, z in zones.items():
        terr = name_of(z.terrain_type)
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
            for p in ("RESOURCE_PILE", "REWARD_PICKUP", "MINE")
        },
    )


def mine_gameplay(level: int, maps: Iterable[OR.FaithfulMap]) -> dict[str, TerrainStats]:
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
    acc = {t: _TerrainAcc() for t in MINED_TERR}
    for fm in maps:
        if level >= len(fm.terrain):
            continue
        _accumulate_map(acc, fm, level)
    return {t: _finish_stats(a) for t, a in acc.items()}


def theta_covariates(st_t: TerrainStats, purpose: str) -> dict[str, list[float]]:
    """The L3 counting fit: th[bin] = log of the purpose's relative intensity in that covariate
    bin vs its zone-wide average (Laplace-smoothed, clipped to ±2). Additive across covariates
    — the log-linear model of spec §7.1 with independent covariate effects."""
    out: dict[str, list[float]] = {}
    tot = sum(st_t.counts.get(p, 0) for p in [purpose]) or 1
    base = tot / max(st_t.tiles, 1)
    for key, cov, tile_bins, nbins in (
        ("e", st_t.e, st_t.tiles_e, EB),
        ("g", st_t.g, st_t.tiles_g, GB),
        ("o", st_t.o, st_t.tiles_o, OB),
    ):
        cnts = cov.get(purpose, [0] * nbins)
        th: list[float] = []
        for b in range(nbins):
            lam_b = (cnts[b] + 0.5) / (tile_bins[b] + 0.5 / max(base, 1e-9))
            th.append(max(-2.0, min(2.0, math.log(lam_b / base))))
        out[key] = th
    return out


def intensity_weights(
    ts: Iterable[Tile], purpose: str, st_t: TerrainStats, cov: Covariates
) -> dict[Tile, float]:
    """Per-tile placement intensity  w(u) = exp(th_e + th_g (+ th_o))  from the L3 fit."""
    th = theta_covariates(st_t, purpose)
    ed, gd, op = cov.ed, cov.gd, cov.op
    w: dict[Tile, float] = {}
    for t in sorted(ts):
        s = th["e"][min(ed[t], EB - 1)] + th["g"][_gbin(gd.get(t, 12))]
        if op is not None:
            s += th["o"][_obin(op[t])] if t in op else -2.0
        w[t] = math.exp(s)
    return w


def info_pool(terrain: str, has_water: bool, has_subterrain: bool = False) -> list[Identity]:
    """`DC.pool("INFO", terrain)`, minus cartographer subtypes the map can't back up:
    cartographerSubterranean is dropped unless the map actually has a second level, and
    cartographerWater is dropped on maps with no water at all."""
    pool = DC.pool("INFO", terrain)
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
    town = next((o for o in objs if o.purpose == "TOWN"), None)
    if town is not None:
        for o in objs:
            if (o.type or "").startswith("randomDwelling"):
                if o.options is None:
                    o.options = {}
                o.options["sameAsTown"] = [town.x, town.y, town.level]


# purposes deliberately NOT reproduced by the generator (the audit's whitelist)
AUDIT_EXCLUDED = {
    "TRANSPORT": "relational: subterranean gates + two-way monoliths are placed by their own "
    + "matched-set passes (place_gate_pairs / PortalStep), not the "
    + "per-zone density draw — the audit must not demand every corpus variant",
    "GUARD": "guards are leveled RANDOM monsters by design, never corpus identities",
}
# corpus sprite VARIANTS of ontology objects: same {type, subtype} gameplay object under a
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
    | {"TOWN", "MINE", "DWELLING", "BANK", "WATER_TRANSPORT"}
) - set(AUDIT_EXCLUDED)


def audit_variety(level: int = 0) -> list[AuditGap]:
    """Corpus-variety audit: every (purpose, animation) with a nonzero corpus count on land
    must (a) resolve through the ontology and (b) be reachable through a generator pool —
    i.e. its purpose is placed and the animation sits in `gameplay_pool` for at least one
    land terrain (or it is an editor RANDOM class, placed by convention). Returns a list of
    `AuditGap`s (empty = the generated maps can reach the corpus's full visitable variety).
    `level` selects which level's corpus stats table to audit (0 = surface, 1 = underground:
    both must stay green since `--subterrain` places gameplay from the level-1 table too)."""
    st = load_gameplay(level=level)
    seen: dict[tuple[str, str], int] = {}  # (purpose, anim) -> total corpus count
    for terr in LAND:
        for p, anims in st[terr].anim_w.items():
            if p in AUDIT_EXCLUDED:
                continue
            for anim, cnt in anims.items():
                seen[(p, anim)] = seen.get((p, anim), 0) + cnt
    pool_anims: dict[str, set[str]] = {}  # purpose -> anims reachable on ANY terrain incl water
    for p in {p for p, _a in seen}:
        pool_anims[p] = {i.animation.lower() for t in (*LAND, "water") for i in DC.pool(p, t)}
    gaps: list[AuditGap] = []
    for (p, raw_anim), cnt in sorted(seen.items(), key=lambda kv: (-kv[1], kv[0])):
        anim = TOWN_SPRITE_VARIANTS.get(raw_anim, raw_anim)
        ident = ON.identity_of(anim)
        if not ON.has_animation(anim):
            gaps.append(AuditGap(p, anim, cnt, "animation missing from the ontology"))
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


class _Args(argparse.Namespace):
    audit: bool = False
    level: int | None = None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    _ = ap.add_argument(
        "--audit",
        action="store_true",
        help="corpus-variety audit: report corpus objects the generator cannot "
        + "reproduce (empty output = full variety reachable). Audits both terrain "
        + "levels (surface + underground) unless --level is given.",
    )
    _ = ap.add_argument("--level", type=int, default=None, help="0=surface, 1=underground")
    args = ap.parse_args(namespace=_Args())
    if args.audit:
        from vcmi_mapgen.cli.settings import load_settings, open_install
        from vcmi_mapgen.vcmi.config import load_config

        ON.use_config(load_config(open_install(load_settings())))
        levels = [args.level] if args.level is not None else [0, 1]
        bad = False
        for lvl in levels:
            gaps = audit_variety(level=lvl)
            print(f"-- level {lvl} --")
            for reason, note in AUDIT_EXCLUDED.items():
                print(f"excluded {reason}: {note}")
            if not gaps:
                print("AUDIT OK: every corpus (purpose, animation) on land is reachable")
            else:
                bad = True
                print(f"AUDIT: {len(gaps)} gaps")
                for g in gaps:
                    print(f"  {g.purpose:<15} {g.anim:<10} corpus n={g.count:>5}  {g.why}")
        raise SystemExit(1 if bad else 0)
    st = load_gameplay(level=args.level or 0)
    for t in LAND:
        d = st[t]
        dens = {p: round(c / max(d.tiles, 1) * 1000, 2) for p, c in d.counts.items()}
        print(
            f"{t:<8} tiles={d.tiles:>7}  per-1000-tiles: {dens}  "
            + f"border_open={d.border_open_frac:.2f}"
        )
        print(f"         guard_frac={d.guard_frac}")

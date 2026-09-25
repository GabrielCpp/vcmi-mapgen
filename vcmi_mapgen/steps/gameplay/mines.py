"""Gameplay object layer — simplified L3 of the marked-point-process spec (§7.1).

Places towns / mines / dwellings / visitable shrines per zone BEFORE vegetation:

  - **counts** come from corpus per-purpose densities (objects per zone tile, mined per
    terrain and cached in ``data/pp/gameplay_stats.json``) — Poisson-style stochastic
    rounding of density x area, with sane per-zone caps,
  - **identities** come from the ontology's `gameplay_pool` (never the corpus); a zone with
    >= 2 mines is guaranteed a sawmill + ore pit first (the H3 economy convention),
  - **placement** is hard-constrained (spec §7.1): the full footprint inside the zone, no
    overlap with other gameplay, and the visitable approach tile free — gameplay objects are
    rigid, unlike vegetation. Objects sit at spread (farthest-point) nodes, towns deepest.

The returned footprint cells + approach tiles feed vegetation's `sample_zone` as `forbid`
(vegetation may never bury gameplay) and the approach tiles become mandatory backbone nodes
(every object reachable through the protected web).
"""

import argparse
import collections
import json
import math
import random
from collections.abc import Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from pathlib import Path

from vcmi_mapgen import ontology as ON
from vcmi_mapgen.kit import json_value as jv
from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.kit.geometry import NB8, edge_dist
from vcmi_mapgen.kit.paths import project_root
from vcmi_mapgen.kit.segmentation import segment_level
from vcmi_mapgen.kit.terrain_lookup import EXCLUDE_DECOR_TYPES, TNAME
from vcmi_mapgen.kit.topology import find_pockets, zone_fronts, zone_gate_bands, zone_gates
from vcmi_mapgen.models import Entrance, Identity, JsonValue, PlacedObject, Tile, Zone

# Gate is the first step in pipeline order to need footprint-fitting helpers
# (footprint_cells/fits/GAP) and rnd_monster; Gameplay/Pickup/Repair import them from there rather
# than duplicating them or inventing a generic shared module (see steps/gate/gates.py).
from vcmi_mapgen.steps.gate.gates import (
    MIN_AREA_STATS,
    NO_TILES,
    Clearance,
    Fit,
    LevelGates,
    fits,
    inflate_gap,
    rnd_monster,
)

ROOT = project_root()
STATS_PATH = str(ROOT / "data" / "pp" / "gameplay_stats.json")
STATS_PATH_UNDERGROUND = str(ROOT / "data" / "pp" / "gameplay_stats_underground.json")
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
CAPS = {"TOWN": 1, "MINE": 8, "DWELLING": 6, "VISIT": 12, "BANK": 4}
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
LAND = ("dirt", "sand", "grass", "snow", "swamp", "rough", "subterr", "lava")
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
ENTRANCE_GUARD_PROB = 0.85  # a planned zone entrance is a genuine chokepoint (the rest of
#                             the border is a vegetation ridge), so it is usually guarded —
#                             vs 0.65 for the legacy wide-open border convention.

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


def _cached_stats(path: Path, force: bool) -> dict[str, TerrainStats] | None:
    if not force and path.exists():
        st = jv.as_object(jv.loads(path.read_text()))
        if st.get("_version") == STATS_VERSION:
            return {k: _stats_from_json(v) for k, v in st.items() if k != "_version"}
    return None


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
        (x, y) for y, row in enumerate(fm.terrain[level]) for x, c in enumerate(row) if c.t == 8
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
        terr = TNAME.get(z.terrain_type)
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


def mine_gameplay(level: int = 0, force: bool = False) -> dict[str, TerrainStats]:
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
    path = Path(STATS_PATH if level == 0 else STATS_PATH_UNDERGROUND)
    cached = _cached_stats(path, force)
    if cached is not None:
        return cached
    acc = {t: _TerrainAcc() for t in MINED_TERR}
    for nm in OR.all_map_names():
        try:
            fm = OR.load_faithful(nm)
        except Exception:
            continue
        if level >= len(fm.terrain):
            continue
        _accumulate_map(acc, fm, level)
    result = {t: _finish_stats(a) for t, a in acc.items()}
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, JsonValue] = {"_version": STATS_VERSION}
    for t, tst in result.items():
        payload[t] = _stats_to_json(tst)
    _ = path.write_text(json.dumps(payload))
    return result


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


_SPIRAL: list[Tile] = sorted(
    ((dx, dy) for dx in range(-5, 6) for dy in range(-5, 6)),
    key=lambda d: (max(abs(d[0]), abs(d[1])), d),
)


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


def _walk_on_only(ident: Identity) -> bool:
    return not any("X" in row for row in ident.mask)


def _info_pool(terrain: str, has_water: bool, has_subterrain: bool = False) -> list[Identity]:
    """`ON.pool("INFO", terrain)`, minus cartographer subtypes the map can't back up:
    cartographerSubterranean is dropped unless the map actually has a second level, and
    cartographerWater is dropped on maps with no water at all."""
    pool = ON.pool("INFO", terrain)
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


@dataclass(frozen=True, slots=True)
class ZoneOptions:
    seed: int = 1
    coastal: AbstractSet[Tile] = NO_TILES
    force_town: bool = False
    ledger: Ledger | None = None
    has_water: bool = False
    level: int = 0
    has_subterrain: bool = False
    avoid: AbstractSet[Tile] = NO_TILES
    preoccupied: AbstractSet[Tile] = NO_TILES
    preblocked: AbstractSet[Tile] = NO_TILES
    preapproaches: Iterable[Tile] = ()
    entrances: Sequence[Entrance] | None = None


DEFAULT_ZONE_OPTIONS = ZoneOptions()


def place_zone(
    ts: AbstractSet[Tile],
    zones: Mapping[int, Zone],
    zid: int,
    terrain: str,
    opts: ZoneOptions = DEFAULT_ZONE_OPTIONS,
) -> LevelGates:
    """Gameplay objects for one zone. Returns (objs, occupied, blocked, approaches):
    `occupied` = every footprint cell (no vegetation there), `blocked` = the impassable
    subset (the walkable web must route around these; approach tiles are never in it).
    objs carry purpose. Deterministic in `seed`.

    Anchors are SAMPLED FROM THE FITTED INTENSITY (towns deep and gate-far, mines mid-depth,
    shrines near routes — whatever the corpus says), not from uniform spread nodes; the GAP
    separation keeps the pattern from clumping.

    Conventions (user-mandated, matching real H3 mapmaking): towns/dwellings are mostly the
    editor's RANDOM classes; a zone with a town always gets a sawmill + ore pit placed NEXT
    TO the town (the start economy); mines get a guard on their approach with the corpus
    guardedness probability (strength ~ resource rarity); every zone gate — the corpus-wide
    open band into the neighbouring zone — gets a random monster at its centre with prob
    0.65 (strength ~ zone size); creature BANKS (utopias, conservatories, crypts) place like
    visitables but carry no extra guard (the bank IS the fight); a coastal zone may get a
    shipyard on the shore (`coastal` = zone tiles touching water). `force_town=True`
    guarantees the zone a town (a designated PLAYER zone).

    `ledger` (optional, shared across the whole map, zones visited in sorted-zid order)
    makes mine types a MAP-level economy: a `Ledger` of `missing` (set of BASIC_MINE_RES not yet
    placed anywhere), `towns` (towns expected+placed so far) and `gold` (gold mines placed so far).
    Zones draw globally-missing resource types first, and a gold mine may only be drawn
    while gold < towns - 1 (gold is worth placing only on multi-town maps).

    `level` (0 = surface, 1 = underground) selects the level's own corpus stats table
    (`mine_gameplay(level=level)`) — real underground density is mined separately, never
    derived from the surface. Placed objects still carry `level=0`; `pp_map.build()` retags the
    whole underground level's objects in one post-processing pass, so this function's
    internal placement logic stays level-agnostic.

    `avoid` (the underground tunnel/gate-connector protect set — empty on the surface) is
    off-limits to every footprint AND approach tile placed here, so a town/mine/monster can
    never wall off a corridor terrain generation already fought to keep connected.

    `preoccupied`/`preblocked`/`preapproaches` seed this zone's occupied/blocked/approach
    state with an object placed BEFORE this zone's own gameplay pass — namely a Subterranean
    Gate (`pp_map.build()` runs `place_gates` right after segmentation, ahead of every zone's
    density pass, so a gate claims its own small footprint first and everything downstream
    — this function's own placements, then vegetation/scatter via the `occupied`/`approaches`
    this function returns — treats it exactly like a pre-existing mine or town: avoided by
    its footprint + the ordinary GAP buffer only, not a large separately-reserved clearing.

    `entrances` (this zone's `kit.topology.plan_entrances` entries, `[(rep, band, other_zid)]`)
    switches the border model from corpus-open gate bands to the map-level ISOLATION plan:
    the planned narrow bands replace `zone_gate_bands` for the gate-distance covariate, no
    gameplay footprint may squat on a band (the crossing must stay walkable), and the
    zone-edge guard pass guards the planned entrance reps directly (prob
    ENTRANCE_GUARD_PROB, single-side ownership zid < other) instead of hunting
    pocket-mouths inside wide-open borders."""
    return _ZonePlacer(ts, zones, zid, terrain, opts).run()


def _mine_variants(ids: list[Identity], mine_w: Mapping[str, int]) -> list[Identity]:
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


def _rest_mines(
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


def _band_union(gate_bands: Sequence[tuple[Tile, AbstractSet[Tile]]]) -> set[Tile]:
    return set[Tile]().union(*(b for _r, b in gate_bands)) if gate_bands else set[Tile]()


def _rim_reserved(
    ts: AbstractSet[Tile], zones: Mapping[int, Zone], zid: int, band_union: AbstractSet[Tile]
) -> frozenset[Tile]:
    # reserve the whole 8-connected rim, not just the bands: a gameplay APPROACH tile
    # sitting on the border is a permanently-walkable hole neither the border bias nor
    # the seal pass may touch (diagonal contact included — corner-cutting is a legal
    # hero move in H3, so a diagonal-only touch tile leaks exactly like a front tile).
    others: set[Tile] = set()
    for zz, z2 in zones.items():
        if zz != zid:
            others.update(z2.tiles_set)
    rim8 = {t for t in ts if any((t[0] + dx, t[1] + dy) in others for dx, dy in NB8)}
    return frozenset(rim8 | band_union)


def _tie_dwellings(objs: list[PlacedObject]) -> None:
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


class _ZonePlacer:
    def __init__(
        self,
        ts: AbstractSet[Tile],
        zones: Mapping[int, Zone],
        zid: int,
        terrain: str,
        opts: ZoneOptions,
    ) -> None:
        self.ts: AbstractSet[Tile] = ts
        self.zones: Mapping[int, Zone] = zones
        self.zid: int = zid
        self.terrain: str = terrain
        self.opts: ZoneOptions = opts
        self.st: TerrainStats = mine_gameplay(level=opts.level)[terrain]
        self.dens: dict[str, float] = {
            p: c / max(self.st.tiles, 1) for p, c in self.st.counts.items()
        }
        self.area: int = len(ts)
        self.rng: random.Random = random.Random(opts.seed ^ (zid * 40503) ^ 0x5EED)
        # FIXED identities from the ontology pools: corpus frequency sqrt-damped and repeats
        # penalized, so rare visitables (star axis, gardens, libraries) actually show up
        self.used_anims: set[str] = set()
        self.wanted: list[tuple[str, Identity]] = []  # (purpose, ident), placement order
        self.ed: dict[Tile, int] = {}
        self.gate_bands: list[tuple[Tile, frozenset[Tile]]] = []
        self.ent_reserved: frozenset[Tile] = NO_TILES
        self.gd: dict[Tile, int] = {}
        self.tiles_sorted: list[Tile] = []
        self.wcache: dict[str, dict[Tile, float]] = {}
        self.objs: list[PlacedObject] = []
        self.occupied: set[Tile] = set(opts.preoccupied)
        self.blocked: set[Tile] = set(opts.preblocked)
        self.approaches: list[Tile] = list(opts.preapproaches)
        self.near: set[Tile] = set()  # occupied inflated by GAP (separation zone)
        self.town_center: tuple[float, float] | None = None  # set once the zone's town settles
        self.town_mines_left: int = 0

    def _stoch(self, x: float, base_cap: int) -> int:
        n = int(x) + (1 if self.rng.random() < x - int(x) else 0)
        return min(n, scaled_cap(base_cap, x))

    def _draw_counts(self) -> tuple[int, int, int, int, int]:
        dens, area, opts, rng = self.dens, self.area, self.opts, self.rng
        n_town = (
            1
            if (
                opts.force_town
                or (area >= TOWN_MIN_AREA and rng.random() < min(1.0, dens.get("TOWN", 0) * area))
            )
            else 0
        )
        n_mine = self._stoch(dens.get("MINE", 0) * area, CAPS["MINE"])
        if n_town:  # a town always brings its economy pair
            n_mine = max(n_mine, 2)
        n_dwell = self._stoch(dens.get("DWELLING", 0) * area, CAPS["DWELLING"])
        n_visit = self._stoch(sum(dens.get(p, 0) for p in VISIT_PURPOSES) * area, CAPS["VISIT"])
        n_bank = self._stoch(dens.get("BANK", 0) * area, CAPS["BANK"])
        if opts.ledger is not None and n_town and not opts.force_town:
            opts.ledger.towns += 1  # player towns are pre-counted by build
        return n_town, n_mine, n_dwell, n_visit, n_bank

    def _pick(self, pool: Iterable[Identity], purpose: str | None = None) -> Identity | None:
        pool = sorted(
            (i for i in pool if "random" not in (i.type or "").lower()),
            key=lambda i: i.animation,
        )
        if not pool:
            return None
        w = self.st.anim_w.get(purpose, {}) if purpose else {}
        weights = [
            (w.get(i.animation.lower(), 0) ** 0.5 + 0.3)
            * (0.05 if i.animation.lower() in self.used_anims else 1.0)
            for i in pool
        ]
        ident = self.rng.choices(pool, weights=weights, k=1)[0]
        self.used_anims.add(ident.animation.lower())
        return ident

    def _town_wanted(self) -> None:
        # PLAYER start towns are ALWAYS randomTown: VCMI resolves an owned random town to
        # the faction the player picked in the lobby (CGTownInstance::randomizeFaction) —
        # a concrete start town would silently override the player's choice. Neutral
        # towns keep the corpus-conventional random/fixed split.
        ident = (
            ON.identity_of(RND_TOWN)
            if self.opts.force_town or self.rng.random() < RANDOM_SHARE
            else self._pick(ON.pool("TOWN", self.terrain), "TOWN")
        )
        if ident:
            self.wanted.append(("TOWN", ident))

    def _take_mine(
        self,
        ids: list[Identity],
        res: str,
        used_res: set[str],
        mine_idents: list[Identity | None],
    ) -> None:
        mine_idents.append(self._pick(ids, "MINE"))
        used_res.add(res)
        ledger = self.opts.ledger
        if ledger is not None:
            ledger.missing.discard(res)
            if res == "goldMine":
                ledger.gold += 1

    def _draw_resource(self, rest: Mapping[str, list[Identity]], mine_w: Mapping[str, int]) -> str:
        ledger = self.opts.ledger
        missing = (ledger.missing & set(rest)) if ledger is not None else set[str]()
        keys = sorted(missing) if missing else sorted(rest)
        rw = [sum(mine_w.get(i.animation.lower(), 0) for i in rest[k]) + 0.2 for k in keys]
        return self.rng.choices(keys, weights=rw, k=1)[0]

    def _mine_wanted(self, n_mine: int) -> None:
        # mines: wood + ore guaranteed first (the H3 economy convention), then DISTINCT further
        # resource types without replacement — a zone gets a gold mine AND a gem pond, not three
        # sawmills (corpus zones rarely duplicate a mine type). With a map `ledger`, globally
        # MISSING basic resources are drawn first (all six minerals covered map-wide) and gold
        # is rationed to towns - 1 (gold mines pay off only on multi-town maps).
        mine_w = self.st.anim_w.get("MINE", {})
        mines = {
            res: _mine_variants(ids, mine_w)
            for res, ids in ON.mines_by_resource(self.terrain).items()
        }
        mine_idents: list[Identity | None] = []
        used_res: set[str] = set()
        if n_mine >= 2:
            for res in ("sawmill", "orePit"):
                if mines.get(res):
                    self._take_mine(mines[res], res, used_res, mine_idents)
        while len(mine_idents) < n_mine:
            rest = _rest_mines(mines, used_res, self.opts.ledger)
            if not rest:
                break
            res = self._draw_resource(rest, mine_w)
            self._take_mine(rest[res], res, used_res, mine_idents)
        self.wanted += [("MINE", i) for i in mine_idents if i]

    def _dwell_wanted(self, n_dwell: int) -> None:
        # dwellings are mostly random (generic or by level, skewed low); fixed dwellings are
        # the deliberate exception in real maps
        rng = self.rng
        pool_dw = ON.pool("DWELLING", self.terrain)
        for _ in range(n_dwell):
            if rng.random() < 0.8:
                anim = (
                    RND_DWELL
                    if rng.random() < 0.3
                    else rng.choices(RND_DWELL_L, weights=(22, 18, 15, 13, 12, 10, 10), k=1)[0]
                )
                ident = ON.identity_of(anim)
            else:
                ident = self._pick(pool_dw, "DWELLING")
            if ident:
                self.wanted.append(("DWELLING", ident))

    def _bank_wanted(self, n_bank: int) -> None:
        # creature banks (utopias, conservatories, crypts, pyramids) — corpus density, no
        # approach guard: the bank IS the fight, its reward is its own
        for _ in range(n_bank):
            ident = self._pick(ON.pool("BANK", self.terrain), "BANK")
            if ident:
                self.wanted.append(("BANK", ident))

    def _visit_wanted(self, n_visit: int) -> None:
        opts, terrain = self.opts, self.terrain
        vw = [self.st.counts.get(p, 0) + 0.2 for p in VISIT_PURPOSES]
        for _ in range(n_visit):
            p = self.rng.choices(VISIT_PURPOSES, weights=vw, k=1)[0]
            pool = (
                _info_pool(terrain, opts.has_water, opts.has_subterrain)
                if p == "INFO"
                else ON.pool(p, terrain)
            )
            ident = self._pick(pool, p)
            if ident:
                self.wanted.append((p, ident))

    def _collect_wanted(self) -> None:
        n_town, n_mine, n_dwell, n_visit, n_bank = self._draw_counts()
        if n_town:
            self._town_wanted()
        self._mine_wanted(n_mine)
        self._dwell_wanted(n_dwell)
        self._bank_wanted(n_bank)
        self._visit_wanted(n_visit)
        self.town_mines_left = 2 if n_town else 0  # sawmill + ore pit anchor NEAR the town

    def _prepare(self) -> None:
        # anchor sampling from the fitted per-purpose intensity (the L3 fit applied).
        # Gates are corpus-wide BANDS of the contact front (not 1-tile corridors) — gate
        # distance is measured from the whole open band, matching the v5 corpus mining.
        ts, opts = self.ts, self.opts
        self.ed = edge_dist(ts)
        if opts.entrances is not None:
            self.gate_bands = [(rep, band) for rep, band, _other in opts.entrances]
            band_union = _band_union(self.gate_bands)
            self.ent_reserved = _rim_reserved(ts, self.zones, self.zid, band_union)
        else:
            self.gate_bands = zone_gate_bands(
                ts, self.zones, self.zid, open_frac=self.st.border_open_frac
            )
            band_union = _band_union(self.gate_bands)
        self.gd = gate_dist(ts, band_union)
        self.tiles_sorted = sorted(ts)
        inflate_gap(self.near, opts.preoccupied)

    def _clearance(self) -> Clearance:
        return Clearance(
            self.occupied, self.near, set(self.approaches) | self.ent_reserved, self.opts.avoid
        )

    def _emit(self, purpose: str, ident: Identity, x: int, y: int) -> None:
        options: dict[str, JsonValue] | None = None
        if purpose == "GUARD":  # absent => VCMI 'compliant' => every creature joins free
            options = {"character": "hostile"}
        elif purpose == "TOWN":  # H3 convention: towns open with a fort, a tavern and
            options = {
                "buildings": {
                    "allOf": [  # the level 1+2 creature dwellings
                        "core:fort",
                        "core:tavern",
                        "core:dwellingLvl1",
                        "core:dwellingLvl2",
                    ]
                },
                "possibleSpells": CORE_SPELLS,  # mage guild teaches from the full pool
            }
        self.objs.append(PlacedObject.at(ident, (x, y), purpose=purpose, options=options))

    def _settle(self, purpose: str, ident: Identity, fit: Fit, node: Tile) -> Tile:
        allc, blk, approach = fit
        self.occupied.update(allc)
        self.blocked.update(blk)
        inflate_gap(self.near, allc)  # inflate: keep the next object GAP away
        self.approaches.append(approach)
        self._emit(purpose, ident, node[0], node[1])
        return approach

    def _seal_cell(self, ident: Identity, x: int, y: int) -> None:
        """Register a 1-cell blocking decoration exactly like `settle` (occupied/blocked/
        GAP-inflated near) but with no approach tile — used to close off a mine's unguarded
        side entrances so its single guard cannot be bypassed. Purpose "MINE_SEAL" (not
        "DECORATION") so it stays distinguishable from ordinary rigid gameplay: it is
        deliberately GAP-adjacent to the mine it seals and has no visitable approach."""
        self.occupied.add((x, y))
        self.blocked.add((x, y))
        inflate_gap(self.near, [(x, y)])
        self._emit("MINE_SEAL", ident, x, y)

    def _candidates(self, purpose: str, ident: Identity) -> tuple[Sequence[Tile], Sequence[Tile]]:
        ts, area = self.ts, self.area
        if purpose == "TOWN" and self.opts.force_town:
            # PLAYER start town: anchored so the footprint CENTER sits on the zone
            # centroid (masks anchor bottom-right, hence the +(w-1)/2 offset). The scan is
            # exhaustive nearest-first over the whole zone — the town is GUARANTEED to
            # place whenever the zone admits its footprint anywhere at all.
            mh = len(ident.mask)
            mw = max(len(r) for r in ident.mask)
            ccx = sum(t[0] for t in ts) / area + (mw - 1) / 2.0
            ccy = sum(t[1] for t in ts) / area + (mh - 1) / 2.0
            cands = sorted(ts, key=lambda t: ((t[0] - ccx) ** 2 + (t[1] - ccy) ** 2, t))
            return cands, ()  # already exhaustive: no nudge needed
        if purpose == "MINE" and self.town_mines_left > 0 and self.town_center is not None:
            # the town's economy pair (sawmill + ore pit, first two MINE entries): an
            # exhaustive nearest-first scan around the town — as close as legality (GAP,
            # approach) admits, guaranteed to place whenever the zone fits it at all
            self.town_mines_left -= 1
            tcx, tcy = self.town_center
            return sorted(ts, key=lambda t: ((t[0] - tcx) ** 2 + (t[1] - tcy) ** 2, t)), ()
        if purpose not in self.wcache:
            self.wcache[purpose] = intensity_weights(
                ts, purpose, self.st, Covariates(self.ed, self.gd)
            )
        wmap = self.wcache[purpose]
        weights = [wmap[t] for t in self.tiles_sorted]
        return self.rng.choices(self.tiles_sorted, weights=weights, k=80), _SPIRAL[:25]

    def _fit_near(
        self, ident: Identity, sampled: Tile, spiral: Sequence[Tile]
    ) -> tuple[Fit | None, Tile]:
        node = sampled
        fit = fits(ident, node, self.ts, self._clearance())
        if fit is None:  # nudge: try a tight spiral at the sample
            for dx, dy in spiral:
                fit = fits(ident, (node[0] + dx, node[1] + dy), self.ts, self._clearance())
                if fit:
                    node = (node[0] + dx, node[1] + dy)
                    break
        return fit, node

    def _mine_front_blocked(self, ident: Identity, fit: Fit) -> bool:
        behind = [(fit[2][0], fit[2][1] + k) for k in range(1, 3 if _walk_on_only(ident) else 2)]
        return any(
            t not in self.ts or t in self.occupied or t in fit[1] or t in self.opts.avoid
            for t in behind
        )

    def _place_one(self, purpose: str, ident: Identity) -> None:
        cands, spiral = self._candidates(purpose, ident)
        for sampled in cands:
            fit, node = self._fit_near(ident, sampled, spiral)
            if fit and purpose == "MINE" and self._mine_front_blocked(ident, fit):
                fit = None
            if fit:
                self._commit(purpose, ident, fit, node)
                break

    def _commit(self, purpose: str, ident: Identity, fit: Fit, node: Tile) -> None:
        approach = self._settle(purpose, ident, fit, node)
        if purpose == "MINE":
            if _walk_on_only(ident):
                approach = (approach[0], approach[1] + 1)
                self.approaches.append(approach)
            self.approaches.append((approach[0], approach[1] + 1))
        if purpose == "TOWN":  # the economy pair anchors around this
            mh = len(ident.mask)
            mw = max(len(r) for r in ident.mask)
            self.town_center = (node[0] - (mw - 1) / 2.0, node[1] - (mh - 1) / 2.0)
        # every mine gets a guard ON the approach (fight to flip), strength ~
        # resource rarity (user-mandated: mines must always be guarded, never left
        # open) — and its 4 other approach-grid tiles (visitableFrom's W/E/SW/SE)
        # are sealed with a blocking decoration so the guard actually gates the
        # mine instead of being trivially walked around from the side.
        if purpose == "MINE":
            self._guard_mine(ident, approach)

    def _guard_mine(self, ident: Identity, approach: Tile) -> None:
        subtype = str(ident.subtype)
        lvl = MINE_GUARD_LVL.get(subtype, 3)
        # sawmill/orePit are the town's starting economy pair — always exactly
        # level 1, never bumped (unlike the rarer mines below).
        if subtype not in ("sawmill", "orePit") and self.rng.random() < 0.25:
            lvl += 1
        gident = rnd_monster(lvl)
        self._emit("GUARD", gident, approach[0], approach[1])
        self.occupied.add(approach)  # no vegetation/pickup may stack there
        ex, ey = approach[0], approach[1] - 1  # the entrance ('X') cell
        seal_pool = ON.decor_pool(
            self.terrain, blocking=True, max_cells=1, exclude_types=EXCLUDE_DECOR_TYPES
        )
        if seal_pool:
            for sx, sy in (
                (ex - 1, ey),
                (ex + 1, ey),
                (ex - 1, ey + 1),
                (ex + 1, ey + 1),
            ):
                if (
                    (sx, sy) in self.ts
                    and (sx, sy) not in self.occupied
                    and (sx, sy) not in self.opts.avoid
                    and (sx, sy) not in self.ent_reserved
                ):
                    self._seal_cell(self.rng.choice(seal_pool), sx, sy)

    def _place_shipyard(self) -> None:
        pool = [i for i in ON.pool("WATER_TRANSPORT", self.terrain) if i.type == "shipyard"] or [
            ON.identity_of("avxshyd0")
        ]
        ident = pool[0]
        cand = sorted(self.opts.coastal)
        self.rng.shuffle(cand)
        for c in cand[:150]:
            fit = fits(ident, c, self.ts, self._clearance())
            if fit:
                _ = self._settle("WATER_TRANSPORT", ident, fit, c)
                break

    def _edge_guard_level(self, per: int) -> int:
        if self.opts.force_town:
            return 1
        return min(7, 1 + self.area // per + (1 if self.rng.random() < 0.4 else 0))

    def _guard_clear(self, gident: Identity, t: Tile) -> bool:
        return all(
            c in self.ts and c not in self.occupied
            for c in OR.mask_interactive_cells(gident.mask, t[0], t[1])
        )

    def _emit_guard_at(self, gident: Identity, target: Tile) -> None:
        self._emit("GUARD", gident, target[0], target[1])
        self.occupied.update(
            (tx, ty) for tx, ty, _b in OR.mask_cells(gident.mask, target[0], target[1])
        )

    def _guard_entrances(self, entrances: Sequence[Entrance]) -> None:
        # zone-edge guards, ISOLATION model: each planned entrance is a genuine chokepoint
        # (the rest of the border densifies into a vegetation ridge — see pp_sample's
        # `border` bias), so the rep itself is worth guarding, at a higher probability and
        # a slightly steeper strength ramp than the old wide-border convention. Only the
        # LOWER zid of the pair emits (single-side ownership — the two sides planned the
        # same aligned crossing, and pp_map's dup-guard cleanup stays as a backstop).
        for rep, band, other in sorted(entrances):
            if self.zid >= other:
                continue
            if self.rng.random() > ENTRANCE_GUARD_PROB:
                continue
            gident = rnd_monster(self._edge_guard_level(200))
            cands = [t for t in [rep, *sorted(band)] if t in self.ts and t not in self.occupied]
            target = next((t for t in cands if self._guard_clear(gident, t)), None)
            if target is None:
                continue
            self._emit_guard_at(gident, target)

    def _guard_pocket_mouths(self) -> None:
        # zone-edge guards: gate bands are deliberately WIDE corpus-open borders (see
        # zone_gate_bands), so most crossings have no real bottleneck at all — guarding an
        # arbitrary "least open" tile inside a wide band never actually blocks anything (the hero
        # just walks around it through the rest of the band). A crossing only deserves a guard
        # when it is a genuine chokepoint: `find_pockets(ts)` finds every tile from which one
        # guard's zone of control seals a bounded (<=16-tile) pocket of this zone's own shape.
        # A gate band tile that is ALSO one of those mouths sits inside a narrow niche that
        # happens to open onto the neighbouring zone — that is worth guarding; a gate band tile
        # that is not is just open ground, and stays unguarded.
        pocket_mouths = find_pockets(self.ts)
        for rep, band in sorted(self.gate_bands):
            cands = [
                t for t in band if t in self.ts and t not in self.occupied and t in pocket_mouths
            ]
            if not cands:
                continue
            target = min(cands, key=lambda t: ((t[0] - rep[0]) ** 2 + (t[1] - rep[1]) ** 2, t))
            if self.rng.random() > 0.65:
                continue
            gident = rnd_monster(self._edge_guard_level(250))
            # only the interactive cell needs to be free/in-zone -- the mask's decorative
            # overlay cells may bleed past the zone edge or over already-blocked scenery, same
            # relaxation as the pickup layer's cache guards (see pp_pickup.put).
            if not self._guard_clear(gident, target):
                continue
            self._emit_guard_at(gident, target)

    def run(self) -> LevelGates:
        self._collect_wanted()
        if not self.wanted:
            return [], set(), set(), []
        self._prepare()
        for purpose, ident in self.wanted:
            self._place_one(purpose, ident)
        # a shipyard on the shore of a coastal zone (mined WATER_TRANSPORT density, boosted for
        # the coastal-only condition) — makes the adjacent water actually navigable
        if self.opts.coastal and self.rng.random() < min(
            0.8, self.dens.get("WATER_TRANSPORT", 0) * self.area * 3
        ):
            self._place_shipyard()
        if self.opts.entrances is not None:
            self._guard_entrances(self.opts.entrances)
        else:
            self._guard_pocket_mouths()
        _tie_dwellings(self.objs)
        return self.objs, self.occupied, self.blocked, self.approaches


# purposes deliberately NOT reproduced by the generator (the audit's whitelist)
AUDIT_EXCLUDED = {
    "TRANSPORT": "relational: subterranean gates + two-way monoliths are placed by their own "
    + "matched-set passes (place_gates / pp_map.rescue_unreachable_zones), not the "
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
    st = mine_gameplay(level=level)
    seen: dict[tuple[str, str], int] = {}  # (purpose, anim) -> total corpus count
    for terr in LAND:
        for p, anims in st[terr].anim_w.items():
            if p in AUDIT_EXCLUDED:
                continue
            for anim, cnt in anims.items():
                seen[(p, anim)] = seen.get((p, anim), 0) + cnt
    pool_anims: dict[str, set[str]] = {}  # purpose -> anims reachable on ANY terrain incl water
    for p in {p for p, _a in seen}:
        pool_anims[p] = {i.animation.lower() for t in (*LAND, "water") for i in ON.pool(p, t)}
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
    zones_by_level: Mapping[int, Mapping[int, Zone]], players: int
) -> list[tuple[int, int]]:
    """Deterministic player-zone pick across BOTH terrain levels (surface always present;
    underground pooled in only when `--subterrain` is on): big land zones that are MUTUALLY
    FAR APART in (x, y) — the two levels share one coordinate system, so cross-level
    distance is compared the same way as same-level distance. Candidates are land zones
    >= 60 tiles, preferring real zones (>= 100 tiles and >= 1/4 of the largest, pooled across
    levels). The first pick is the largest zone overall; each next pick greedily maximizes
    the minimum centroid distance to the zones already chosen (tie-break: area desc, level,
    zid). Returns [(level, zid), ...] in player order."""
    cand = [
        (z.area, level, zid, z.centroid)
        for level, zones in zones_by_level.items()
        for zid, z in zones.items()
        if TNAME.get(z.terrain_type) in LAND and z.area >= 60
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
    st = mine_gameplay(level=args.level or 0)
    for t in LAND:
        d = st[t]
        dens = {p: round(c / max(d.tiles, 1) * 1000, 2) for p, c in d.counts.items()}
        print(
            f"{t:<8} tiles={d.tiles:>7}  per-1000-tiles: {dens}  "
            + f"border_open={d.border_open_frac:.2f}"
        )
        print(f"         guard_frac={d.guard_frac}")

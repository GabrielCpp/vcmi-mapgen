"""Subterranean Gate placement — Gate-only logic split out of pp_gameplay.py.

Also owns the low-level gameplay-footprint fitting helpers (`footprint_cells`/`fits`/`GAP`) and
`rnd_monster`: GateStep is the first step in pipeline order to need them, and the later
placement steps (which need the same helpers for mines, pocket guards, and portal rescue)
import them from here rather than duplicating them or inventing a generic shared module.
"""

import json
import math
import random
from collections.abc import Container, Iterable, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from itertools import combinations

from vcmi_mapgen import ontology as ON
from vcmi_mapgen.kit import json_value as jv
from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.kit.paths import project_root
from vcmi_mapgen.models import Identity, PlacedObject, Tile

ROOT = project_root()
GATE_STATS_PATH = ROOT / "data" / "pp" / "gate_stats.json"
GATE_STATS_VERSION = 2
MIN_GAP_QUANTILE = 0.25
NO_TILES: frozenset[Tile] = frozenset()
MIN_AREA_STATS = 60

GATE_ANIM = "avtcave"  # SUBTERRANEAN_GATE — single un-suffixed sprite variant

RND_MON = tuple(f"avwmon{i}" for i in range(1, 8))  # randomMonsterLevel 1..7

GAP = 2  # free tiles kept between any two gameplay footprints — gameplay
# neighbours VEGETATION (which fills the gap), not other gameplay


@dataclass(frozen=True, slots=True)
class GateStats:
    """Corpus gate estimator: the gate counts of two-level corpus maps grouped by map width,
    and the closest-pair gate gap as a fraction of map width."""

    counts_by_size: Mapping[int, tuple[int, ...]]
    min_gap_frac: float
    n_maps: int

    def draw_count(self, size: int, rng: random.Random) -> int:
        """A gate count drawn from corpus maps of the nearest width."""
        if not self.counts_by_size:
            return 1
        width = min(self.counts_by_size, key=lambda w: (abs(w - size), w))
        return rng.choice(self.counts_by_size[width])

    def min_gap(self, size: int) -> float:
        return self.min_gap_frac * size


type Fit = tuple[list[Tile], list[Tile], Tile]
type LevelGates = tuple[list[PlacedObject], set[Tile], set[Tile], list[Tile]]


def rnd_monster(lvl: int) -> Identity:
    """Random-monster identity of a level, clamped to 1..7."""
    return ON.identity_of(RND_MON[max(1, min(7, int(lvl))) - 1])


def footprint_cells(
    ident: Identity, ax: int, ay: int
) -> tuple[list[Tile], list[Tile], Tile | None]:
    """(all_cells, blocking_cells, approach) of an identity anchored at (ax, ay); approach is
    the tile a hero stands on to visit ('X' = enter from below; 'A' = the tile itself)."""
    allc: list[Tile] = []
    blk: list[Tile] = []
    approach: Tile | None = None
    rows = ident.mask
    hh = len(rows)
    for r, row in enumerate(rows):
        ww = len(row)
        for ci, ch in enumerate(row):
            if ch == " ":
                continue
            tx, ty = ax - (ww - 1 - ci), ay - (hh - 1 - r)
            allc.append((tx, ty))
            if ch in ("B", "X"):
                blk.append((tx, ty))
            if ch == "X":
                approach = (tx, ty + 1)
            elif ch == "A" and approach is None:
                approach = (tx, ty)
    return allc, blk, approach


@dataclass(frozen=True, slots=True)
class Clearance:
    occupied: Container[Tile]
    near: Container[Tile]
    reserved: Container[Tile]
    avoid: Container[Tile] = NO_TILES


def fits(ident: Identity, anchor: Tile, ts: Container[Tile], clear: Clearance) -> Fit | None:
    """Legality: whole footprint in-zone, at least GAP free tiles from every other gameplay
    footprint (`near` = existing cells inflated by GAP), no squatting on an earlier object's
    approach tile (`reserved`), own approach tile in-zone and standable. `avoid` (the
    underground tunnel/gate-connector protect set — empty on the surface) keeps gameplay
    footprints off cells terrain generation already fought to keep walkable: those cells
    are guarded from vegetation via `protected_web`, but gameplay placement runs BEFORE
    that web is built, so without this check a town/mine/monster footprint could still
    silently wall off a corridor that vegetation would otherwise have left alone."""
    allc, blk, approach = footprint_cells(ident, anchor[0], anchor[1])
    if approach is None:
        return None
    for cell in allc:
        if cell not in ts or cell in clear.near or cell in clear.reserved or cell in clear.avoid:
            return None
    if (
        approach not in ts
        or approach in clear.occupied
        or approach in blk
        or approach in clear.avoid
    ):
        return None
    return allc, blk, approach


def _corpus_gates(fm: OR.FaithfulMap) -> tuple[Tile, ...]:
    return tuple(
        sorted(
            (o.x, o.y)
            for o in fm.objects
            if o.level == 0 and (o.animation or "").lower().removesuffix(".def") == GATE_ANIM
        )
    )


def _load_gate_stats() -> GateStats | None:
    if not GATE_STATS_PATH.exists():
        return None
    st = jv.as_object(jv.loads(GATE_STATS_PATH.read_text()))
    if st.get("_version") != GATE_STATS_VERSION:
        return None
    frac = st.get("min_gap_frac")
    return GateStats(
        counts_by_size={
            int(w): tuple(jv.as_int(n) for n in jv.as_list(ns))
            for w, ns in jv.as_object(st.get("counts_by_size")).items()
        },
        min_gap_frac=float(frac) if isinstance(frac, int | float) else 0.0,
        n_maps=jv.as_int(st.get("n_maps")),
    )


def mine_gate_stats(force: bool = False) -> GateStats:
    """Corpus SUBTERRANEAN_GATE estimator over distinct two-level corpus maps with at least
    one gate. Gate count does not track underground area in the corpus, so the count is a
    draw from same-width maps rather than a per-tile rate. The spacing floor is the
    MIN_GAP_QUANTILE quantile of each multi-gate map's closest gate pair."""
    if not force and (cached := _load_gate_stats()) is not None:
        return cached
    counts: dict[int, list[int]] = {}
    gaps: list[float] = []
    seen: set[tuple[int, tuple[Tile, ...]]] = set()
    for nm in OR.all_map_names():
        try:
            fm = OR.load_faithful(nm)
        except Exception:
            continue
        if len(fm.terrain) < 2:
            continue
        if sum(1 for row in fm.terrain[1] for c in row if c.t != 9) < MIN_AREA_STATS:
            continue
        gates = _corpus_gates(fm)
        if not gates or (fm.width, gates) in seen:
            continue
        seen.add((fm.width, gates))
        counts.setdefault(fm.width, []).append(len(gates))
        if len(gates) >= 2:
            gaps.append(min(math.dist(a, b) for a, b in combinations(gates, 2)) / fm.width)
    gaps.sort()
    frac = gaps[int(MIN_GAP_QUANTILE * (len(gaps) - 1))] if gaps else 0.0
    by_size = {w: sorted(ns) for w, ns in sorted(counts.items())}
    GATE_STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ = GATE_STATS_PATH.write_text(
        json.dumps(
            {
                "_version": GATE_STATS_VERSION,
                "counts_by_size": {str(w): ns for w, ns in by_size.items()},
                "min_gap_frac": frac,
                "n_maps": len(seen),
            }
        )
    )
    return GateStats(
        counts_by_size={w: tuple(ns) for w, ns in by_size.items()},
        min_gap_frac=frac,
        n_maps=len(seen),
    )


@dataclass(frozen=True, slots=True)
class GateSide:
    ts: AbstractSet[Tile]
    occ: Iterable[Tile]
    appr: Iterable[Tile] = NO_TILES
    zone_of: Mapping[Tile, int] = field(default_factory=dict[Tile, int])


def inflate_gap(near: set[Tile], cells: Iterable[Tile]) -> None:
    for cx, cy in cells:
        for gx in range(-GAP, GAP + 1):
            for gy in range(-GAP, GAP + 1):
                near.add((cx + gx, cy + gy))


@dataclass
class _Spread:
    side0: GateSide
    side1: GateSide
    min_gap: float
    used0: set[int] = field(default_factory=set)
    used1: set[int] = field(default_factory=set)
    anchors: list[Tile] = field(default_factory=list)

    def admits(self, c: Tile) -> bool:
        if self.side0.zone_of.get(c, -1) in self.used0:
            return False
        if self.side1.zone_of.get(c, -1) in self.used1:
            return False
        return all(math.dist(c, a) >= self.min_gap for a in self.anchors)

    def take(self, c: Tile) -> None:
        self.anchors.append(c)
        for zone_of, used in ((self.side0.zone_of, self.used0), (self.side1.zone_of, self.used1)):
            if c in zone_of:
                used.add(zone_of[c])


def place_gates(
    side0: GateSide, side1: GateSide, size: int, seed: int = 1
) -> tuple[LevelGates, LevelGates]:
    """Subterranean Gate pairs: one `avtcave` object at the IDENTICAL (x, y) on both levels —
    `kit/reachability.py`'s `_gate_links` already pairs gates by exact-(x, y) match, so no other
    linking is needed. Candidates are tiles walkable on BOTH levels (`ts0 & ts1`); footprint
    legality (`fits`, reused unchanged) is checked against the UNION of both levels' already-
    placed gameplay footprints (`occ0`/`occ1`, GAP-inflated the same way `place_zone` does
    internally) plus their existing approach tiles (`appr0`/`appr1`, so a gate can never
    squat on a mine's or town's doorway), so a gate can never land on top of existing
    objects on either side. The gate count is drawn from corpus maps of the same width
    (`mine_gate_stats`) and is an upper bound. Each zone (`zone_of`) on either level hosts at
    most one gate, and no two gates sit closer than the corpus spacing floor, so pairs spread
    across the map instead of clustering in one big zone. The underground-side approach — the
    harder, descending direction — gets a random monster guard at the corpus zone-gate
    probability (0.65, matching `place_zone`'s own gate-band convention); the surface side is
    left open.

    Returns `(objs0, occ0, blk0, appr0), (objs1, occ1, blk1, appr1)` — the same 4-tuple shape
    `place_zone` returns per level, so `pp_map.build()` folds gate placement into its existing
    per-level object/occupied/blocked/approach aggregation with no special-casing."""
    rng = random.Random(seed ^ 0x6A7E)
    objs0: list[PlacedObject] = []
    objs1: list[PlacedObject] = []
    occ0n: set[Tile] = set()
    occ1n: set[Tile] = set()
    blk0n: set[Tile] = set()
    blk1n: set[Tile] = set()
    appr0n: list[Tile] = []
    appr1n: list[Tile] = []
    ts_both = side0.ts & side1.ts
    if not ts_both:
        return (objs0, occ0n, blk0n, appr0n), (objs1, occ1n, blk1n, appr1n)
    st = mine_gate_stats()
    target = st.draw_count(size, rng)
    spread = _Spread(side0, side1, st.min_gap(size))
    ident = ON.identity_of(GATE_ANIM)
    cands = sorted(ts_both)
    rng.shuffle(cands)
    occupied = set(side0.occ) | set(side1.occ)
    near: set[Tile] = set()
    inflate_gap(near, occupied)
    reserved = set(side0.appr) | set(side1.appr)
    for c in cands:
        if len(objs0) >= target:
            break
        if not spread.admits(c):
            continue
        fit = fits(ident, c, ts_both, Clearance(occupied, near, reserved))
        if fit is None:
            continue
        allc, blk, approach = fit
        occupied.update(allc)
        inflate_gap(near, allc)
        reserved.add(approach)
        spread.take(c)
        for lvl, objs, occn, blkn, apprn in (
            (0, objs0, occ0n, blk0n, appr0n),
            (1, objs1, occ1n, blk1n, appr1n),
        ):
            objs.append(PlacedObject.at(ident, c, level=lvl, purpose="TRANSPORT"))
            occn.update(allc)
            blkn.update(blk)
            apprn.append(approach)
        if rng.random() < 0.65:  # guard only the underground (descending) approach
            gident = rnd_monster(3)
            objs1.append(
                PlacedObject.at(
                    gident,
                    approach,
                    level=1,
                    purpose="GUARD",
                    options={"character": "hostile"},
                )
            )
            occ1n.add(approach)
    return (objs0, occ0n, blk0n, appr0n), (objs1, occ1n, blk1n, appr1n)

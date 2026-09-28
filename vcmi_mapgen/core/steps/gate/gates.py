"""Subterranean Gate statistics and spreading, and the gameplay-footprint fitting helpers
(`footprint_cells`/`fits`/`GAP`) and `rnd_monster` every placement step shares.
"""

import math
import random
from collections.abc import Callable, Container, Iterable, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from itertools import combinations

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Identity, MapState, Role, Tile
from vcmi_mapgen.kit import pp_cache
from vcmi_mapgen.kit.paths import project_root
from vcmi_mapgen.vcmi.formats import json_value as jv

ROOT = project_root()
GATE_STATS_PATH = ROOT / "data" / "pp" / "gate_stats.json"
GATE_STATS_VERSION = 2
GATE_STATS_SOURCE = "vcmi_mapgen.core.steps.gate.gates.mine_gate_stats"
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


def rnd_monster(catalog: Catalog, lvl: int) -> Identity:
    """Random-monster identity of a level, clamped to 1..7."""
    return catalog.identity_of(RND_MON[max(1, min(7, int(lvl))) - 1])


def footprint_cells(
    ident: Identity, ax: int, ay: int
) -> tuple[list[Tile], list[Tile], Tile | None]:
    """(all_cells, blocking_cells, approach) of an identity anchored at (ax, ay); approach is
    the tile a hero stands on to visit: below an entrance, or a visit cell itself."""
    allc: list[Tile] = []
    blk: list[Tile] = []
    approach: Tile | None = None
    for (tx, ty), role in ident.footprint.at(ax, ay):
        allc.append((tx, ty))
        if role.blocks:
            blk.append((tx, ty))
        if role is Role.ENTRANCE:
            approach = (tx, ty + 1)
        elif role is Role.VISIT and approach is None:
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
    approach tile (`reserved`), own approach tile in-zone and standable. No cell and no
    approach may touch `avoid`, the ground a later object has claimed."""
    allc, blk, approach = footprint_cells(ident, anchor[0], anchor[1])
    if approach is None:
        return None
    for cell in allc:
        if cell not in ts or cell in clear.near or cell in clear.reserved or cell in clear.avoid:
            return None
    if approach not in ts or approach in clear.occupied or approach in blk:
        return None
    if approach in clear.avoid:
        return None
    return allc, blk, approach


def _corpus_gates(fm: MapState) -> tuple[Tile, ...]:
    return tuple(
        sorted(
            (o.x, o.y)
            for o in fm.objs
            if o.level == 0 and (o.animation or "").lower().removesuffix(".def") == GATE_ANIM
        )
    )


def load_gate_stats() -> GateStats:
    st = pp_cache.read(GATE_STATS_PATH, version=GATE_STATS_VERSION)
    frac = st.get("min_gap_frac")
    return GateStats(
        counts_by_size={
            int(w): tuple(jv.as_int(n) for n in jv.as_list(ns))
            for w, ns in jv.as_object(st.get("counts_by_size")).items()
        },
        min_gap_frac=float(frac) if isinstance(frac, int | float) else 0.0,
        n_maps=jv.as_int(st.get("n_maps")),
    )


def save_gate_stats(st: GateStats) -> None:
    pp_cache.write(
        GATE_STATS_PATH,
        GATE_STATS_SOURCE,
        {
            "_version": GATE_STATS_VERSION,
            "counts_by_size": {str(w): list(ns) for w, ns in st.counts_by_size.items()},
            "min_gap_frac": st.min_gap_frac,
            "n_maps": st.n_maps,
        },
    )


def mine_gate_stats(maps: Iterable[MapState]) -> GateStats:
    """Corpus SUBTERRANEAN_GATE estimator over distinct two-level corpus maps with at least
    one gate. Gate count does not track underground area in the corpus, so the count is a
    draw from same-width maps rather than a per-tile rate. The spacing floor is the
    MIN_GAP_QUANTILE quantile of each multi-gate map's closest gate pair."""
    counts: dict[int, list[int]] = {}
    gaps: list[float] = []
    seen: set[tuple[int, tuple[Tile, ...]]] = set()
    for fm in maps:
        if len(fm.cells) < 2:
            continue
        if sum(1 for row in fm.cells[1] for c in row if c.t != 9) < MIN_AREA_STATS:
            continue
        gates = _corpus_gates(fm)
        if not gates or (fm.size, gates) in seen:
            continue
        seen.add((fm.size, gates))
        counts.setdefault(fm.size, []).append(len(gates))
        if len(gates) >= 2:
            gaps.append(min(math.dist(a, b) for a, b in combinations(gates, 2)) / fm.size)
    gaps.sort()
    frac = gaps[int(MIN_GAP_QUANTILE * (len(gaps) - 1))] if gaps else 0.0
    by_size = {w: sorted(ns) for w, ns in sorted(counts.items())}
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
class Spread:
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


def gate_anchors(
    side0: GateSide,
    side1: GateSide,
    size: int,
    seed: int,
    place: Callable[[Tile, Spread], Tile | None],
) -> list[Tile]:
    """Walk the tiles land on both levels in a seeded order and let ``place`` put a gate
    pair near each one the spread admits. ``place`` returns the anchor it used, or None.
    The count is drawn from corpus maps of the same width and is an upper bound. Each zone
    on either level hosts at most one gate, and no two gates sit closer than the corpus
    spacing floor."""
    rng = random.Random(seed ^ 0x6A7E)
    ts_both = side0.ts & side1.ts
    if not ts_both:
        return []
    st = load_gate_stats()
    target = st.draw_count(size, rng)
    spread = Spread(side0, side1, st.min_gap(size))
    cands = sorted(ts_both)
    rng.shuffle(cands)
    out: list[Tile] = []
    for c in cands:
        if len(out) >= target:
            break
        if not spread.admits(c):
            continue
        anchor = place(c, spread)
        if anchor is None:
            continue
        spread.take(anchor)
        out.append(anchor)
    return out
